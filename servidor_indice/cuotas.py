"""Cuota diaria: gratis para las personas, de pago para el uso a escala.

Decisión de producto del 29-sep-2026: quien consulta lo razonable no paga ni se
registra; quien consulta por volumen (integración comercial, extracción masiva)
necesita una clave de pago con su propio tope.

La forma de contar tiene que respetar la regla 2 del proyecto —no se identifica
a quien pregunta—, así que:

- **La IP nunca se guarda.** Se cuenta por `HMAC(sal, ip)`, con una sal aleatoria
  que vive solo en memoria y se renueva cada día. Pasado el día, ni el operador
  del servidor puede saber qué IP hizo qué: la sal ya no existe.
- **Solo se guarda un número por huella**, nunca la consulta. Todo se borra al
  cambiar el día y nada toca el disco.
- Las claves de pago se guardan **por su hash** (`ALIADO_CLAVES_API`), nunca en
  claro: filtrar el archivo no filtra las claves.

Límites conocidos, dichos para que nadie los tome por muralla: una IP compartida
(universidad, café, datos móviles con NAT) suma a varias personas, y quien quiera
abusar puede rotar IPs. El tope separa lo casual de lo masivo; no lo impide.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

TOPE_IP_DEFECTO = 30
# Día de Colombia (UTC-5, sin horario de verano): el tope se renueva a
# medianoche de quien consulta, no del servidor.
ZONA = timedelta(hours=-5)
# Tope de huellas en memoria: con esto un ataque de IPs aleatorias no llena la
# RAM. Al pasarlo, las huellas nuevas cuentan como agotadas hasta el día siguiente.
MAX_HUELLAS = 200_000


def hoy(ahora: datetime | None = None) -> str:
    return ((ahora or datetime.now(UTC)) + ZONA).date().isoformat()


def segundos_hasta_manana(ahora: datetime | None = None) -> int:
    local = (ahora or datetime.now(UTC)) + ZONA
    manana = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((manana - local).total_seconds()))


def hash_clave(clave: str) -> str:
    return hashlib.sha256(clave.strip().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Plan:
    nombre: str
    tope_diario: int | None  # None = sin tope


def cargar_claves(texto: str | None) -> dict[str, Plan]:
    """`ALIADO_CLAVES_API`: JSON {"<sha256 de la clave>": {"nombre": .., "tope_diario": N}}.

    Se admite también la ruta a un archivo con ese JSON. Una entrada mal formada
    se descarta en vez de tumbar el servidor.
    """
    if not texto or not texto.strip():
        return {}
    crudo = texto.strip()
    if not crudo.startswith("{") and os.path.isfile(crudo):
        with open(crudo, encoding="utf-8") as f:
            crudo = f.read()
    try:
        datos = json.loads(crudo)
    except ValueError:
        return {}
    planes = {}
    for h, v in (datos or {}).items():
        if not isinstance(v, dict) or len(h) != 64:
            continue
        tope = v.get("tope_diario")
        if tope is not None and (isinstance(tope, bool) or not isinstance(tope, int) or tope < 0):
            continue
        planes[h.lower()] = Plan(str(v.get("nombre") or "cliente"), tope)
    return planes


@dataclass
class Veredicto:
    permitido: bool
    tope: int | None
    usadas: int
    via: str  # "operador" | "clave" | "ip"

    @property
    def restantes(self) -> int | None:
        return None if self.tope is None else max(0, self.tope - self.usadas)


class Cuotas:
    def __init__(self, tope_ip: int = TOPE_IP_DEFECTO, claves: dict[str, Plan] | None = None):
        self.tope_ip = tope_ip
        self.claves = claves or {}
        self._lock = threading.Lock()
        self._dia = ""
        self._sal = b""
        self._contador: dict[str, int] = {}

    @classmethod
    def desde_entorno(cls) -> Cuotas:
        try:
            tope = int(os.environ.get("ALIADO_TOPE_DIARIO_IP", TOPE_IP_DEFECTO))
        except ValueError:
            tope = TOPE_IP_DEFECTO
        return cls(max(0, tope), cargar_claves(os.environ.get("ALIADO_CLAVES_API")))

    def _renovar_si_cambio_el_dia(self, ahora: datetime | None) -> None:
        dia = hoy(ahora)
        if dia != self._dia:
            # La sal del día anterior desaparece con él: sus huellas ya no se
            # pueden volver a calcular a partir de una IP.
            self._dia = dia
            self._sal = secrets.token_bytes(32)
            self._contador = {}

    def _huella_ip(self, ip: str) -> str:
        return "ip:" + hmac.new(self._sal, ip.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def plan_de(self, clave: str | None) -> Plan | None:
        return self.claves.get(hash_clave(clave)) if clave else None

    def consumir(self, ip: str, clave: str | None = None, ahora: datetime | None = None) -> Veredicto:
        """Cuenta una consulta y dice si pasa. Una clave desconocida NO cae a la
        cuota por IP: el llamador responde 401, para que un error de tipeo en una
        clave de pago no se confunda con haber agotado el tope."""
        with self._lock:
            self._renovar_si_cambio_el_dia(ahora)
            if clave is not None:
                h = hash_clave(clave)
                plan = self.claves[h]
                huella, tope, via = "clave:" + h[:32], plan.tope_diario, "clave"
            else:
                huella, tope, via = self._huella_ip(ip), self.tope_ip, "ip"
            usadas = self._contador.get(huella, 0)
            if huella not in self._contador and len(self._contador) >= MAX_HUELLAS:
                return Veredicto(False, tope, tope or 0, via)
            if tope is not None and usadas >= tope:
                return Veredicto(False, tope, usadas, via)
            self._contador[huella] = usadas + 1
            return Veredicto(True, tope, usadas + 1, via)

    def estado_interno(self) -> dict:
        """Solo para pruebas: lo que hay en memoria. Nunca debe contener una IP."""
        with self._lock:
            return {"dia": self._dia, "huellas": dict(self._contador)}
