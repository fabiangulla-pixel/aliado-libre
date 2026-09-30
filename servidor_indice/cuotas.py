"""Cuota diaria: gratis para las personas, de pago para el uso a escala.

Modelo decidido el 29-sep-2026 (freemium):

- **Anónimo**: gratis. A partir de `ALIADO_TOPE_APORTE` (15) consultas en el día
  se sugiere un aporte voluntario, sin bloquear; a partir de
  `ALIADO_TOPE_DIARIO_IP` (30) se bloquea hasta medianoche.
- **Claves de pago** (`ALIADO_CLAVES_API`): cada plan con su tope, su periodo
  (día o mes) y, si aplica, su fecha de vencimiento (pase de un día, membresía
  mensual, Gold por π años).
- **Operador**: sin tope.

La forma de contar a los anónimos respeta la regla 2 del proyecto —no se
identifica a quien pregunta—:

- **La IP nunca se guarda.** Se cuenta por `HMAC(sal, ip)`, con una sal aleatoria
  que vive solo en memoria y se renueva cada día. Pasado el día, ni el operador
  del servidor puede saber qué IP hizo qué: la sal ya no existe. Por eso el
  servidor NO puede saber si un anónimo volvió otro día; las sugerencias de
  membresía por uso mensual las calcula el propio equipo de la persona.
- **Solo se guarda un número por huella**, nunca la consulta.

Con las claves es distinto, y está bien que lo sea: quien paga se identificó con
su clave. Su uso del periodo se cuenta por el hash de la clave y, si se da
`ALIADO_USO_CLAVES`, se guarda en disco para sobrevivir a un reinicio. Nunca la
consulta, nunca la IP.

Límites conocidos: una IP compartida (universidad, café, NAT de datos móviles)
suma a varias personas, y quien quiera abusar puede rotar IPs. El tope separa lo
casual de lo masivo; no lo impide.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

TOPE_APORTE_DEFECTO = 15
TOPE_IP_DEFECTO = 30
# Día de Colombia (UTC-5, sin horario de verano): el tope se renueva a
# medianoche de quien consulta, no del servidor.
ZONA = timedelta(hours=-5)
# Tope de huellas en memoria: con esto un ataque de IPs aleatorias no llena la
# RAM. Al pasarlo, las huellas nuevas cuentan como agotadas hasta el día siguiente.
MAX_HUELLAS = 200_000
PERIODOS = ("dia", "mes")


def ahora_local(ahora: datetime | None = None) -> datetime:
    return (ahora or datetime.now(UTC)) + ZONA


def hoy(ahora: datetime | None = None) -> str:
    return ahora_local(ahora).date().isoformat()


def segundos_hasta_manana(ahora: datetime | None = None) -> int:
    local = ahora_local(ahora)
    manana = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((manana - local).total_seconds()))


def id_periodo(periodo: str, ahora: datetime | None = None) -> str:
    d = ahora_local(ahora).date()
    return d.isoformat() if periodo == "dia" else f"{d.year:04d}-{d.month:02d}"


def hash_clave(clave: str) -> str:
    return hashlib.sha256(clave.strip().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Plan:
    nombre: str
    tope: int | None  # None = sin tope
    periodo: str = "dia"  # "dia" | "mes": cada cuánto se renueva el tope
    vence: date | None = None  # último día de validez, inclusive


def _plan_desde_dict(v: dict) -> Plan | None:
    # "tope_diario" es el formato del 29-sep (antes de los periodos): se acepta.
    tope = v.get("tope", v.get("tope_diario"))
    if tope is not None and (isinstance(tope, bool) or not isinstance(tope, int) or tope < 0):
        return None
    periodo = v.get("periodo", "dia")
    if periodo not in PERIODOS:
        return None
    vence = v.get("vence")
    if vence is not None:
        try:
            vence = date.fromisoformat(vence)
        except (TypeError, ValueError):
            return None
    return Plan(str(v.get("nombre") or "cliente"), tope, periodo, vence)


def cargar_claves(texto: str | None) -> dict[str, Plan]:
    """`ALIADO_CLAVES_API`: JSON {"<sha256 de la clave>": {"nombre", "tope",
    "periodo", "vence"}} o la ruta a un archivo con ese JSON. Una entrada mal
    formada se descarta en vez de tumbar el servidor."""
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
        if (plan := _plan_desde_dict(v)) is not None:
            planes[h.lower()] = plan
    return planes


@dataclass
class Veredicto:
    permitido: bool
    tope: int | None
    usadas: int
    via: str  # "clave" | "ip"
    sugerir_aporte: bool = False
    vencida: bool = False
    periodo: str = "dia"

    @property
    def restantes(self) -> int | None:
        return None if self.tope is None else max(0, self.tope - self.usadas)


class Cuotas:
    def __init__(
        self,
        tope_ip: int = TOPE_IP_DEFECTO,
        claves: dict[str, Plan] | None = None,
        tope_aporte: int | None = TOPE_APORTE_DEFECTO,
        ruta_uso_claves: str | None = None,
    ):
        self.tope_ip = tope_ip
        self.tope_aporte = tope_aporte
        self.claves = claves or {}
        self.ruta_uso_claves = ruta_uso_claves
        self._lock = threading.Lock()
        self._dia = ""
        self._sal = b""
        self._contador: dict[str, int] = {}
        # hash de clave -> [id del periodo, usadas]. Separado del contador de
        # anónimos: ese se borra cada día; este dura lo que dure el periodo.
        self._uso_claves: dict[str, list] = self._leer_uso_claves()

    @classmethod
    def desde_entorno(cls) -> Cuotas:
        def entero(var: str, defecto: int) -> int:
            try:
                return max(0, int(os.environ.get(var, defecto)))
            except ValueError:
                return defecto

        return cls(
            entero("ALIADO_TOPE_DIARIO_IP", TOPE_IP_DEFECTO),
            cargar_claves(os.environ.get("ALIADO_CLAVES_API")),
            entero("ALIADO_TOPE_APORTE", TOPE_APORTE_DEFECTO),
            os.environ.get("ALIADO_USO_CLAVES") or None,
        )

    # -- persistencia del uso de las claves de pago ------------------------

    def _leer_uso_claves(self) -> dict[str, list]:
        if not self.ruta_uso_claves or not os.path.isfile(self.ruta_uso_claves):
            return {}
        try:
            with open(self.ruta_uso_claves, encoding="utf-8") as f:
                datos = json.load(f)
            return {k: v for k, v in datos.items() if isinstance(v, list) and len(v) == 2}
        except (OSError, ValueError):
            return {}

    def _guardar_uso_claves(self) -> None:
        if not self.ruta_uso_claves:
            return
        temporal = self.ruta_uso_claves + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(self._uso_claves, f)
        os.replace(temporal, self.ruta_uso_claves)  # atómico: un corte no deja medio archivo

    # -- conteo ------------------------------------------------------------

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
                return self._consumir_clave(hash_clave(clave), ahora)
            huella = self._huella_ip(ip)
            usadas = self._contador.get(huella, 0)
            if huella not in self._contador and len(self._contador) >= MAX_HUELLAS:
                return Veredicto(False, self.tope_ip, self.tope_ip, "ip")
            if usadas >= self.tope_ip:
                return Veredicto(False, self.tope_ip, usadas, "ip")
            self._contador[huella] = usadas + 1
            sugerir = self.tope_aporte is not None and usadas + 1 > self.tope_aporte
            return Veredicto(True, self.tope_ip, usadas + 1, "ip", sugerir_aporte=sugerir)

    def _consumir_clave(self, h: str, ahora: datetime | None) -> Veredicto:
        plan = self.claves[h]
        if plan.vence is not None and ahora_local(ahora).date() > plan.vence:
            return Veredicto(False, plan.tope, 0, "clave", vencida=True, periodo=plan.periodo)
        periodo = id_periodo(plan.periodo, ahora)
        actual_periodo, usadas = self._uso_claves.get(h, [periodo, 0])
        if actual_periodo != periodo:
            usadas = 0
        if plan.tope is not None and usadas >= plan.tope:
            return Veredicto(False, plan.tope, usadas, "clave", periodo=plan.periodo)
        self._uso_claves[h] = [periodo, usadas + 1]
        self._guardar_uso_claves()
        return Veredicto(True, plan.tope, usadas + 1, "clave", periodo=plan.periodo)

    def estado_interno(self) -> dict:
        """Solo para pruebas: lo que hay en memoria. Nunca debe contener una IP."""
        with self._lock:
            return {"dia": self._dia, "huellas": dict(self._contador), "claves": dict(self._uso_claves)}


# -- mensajes a la persona ---------------------------------------------------
# El enlace de pago es configurable: hasta que exista pasarela (Nequi, PSE…)
# apunta al correo del proyecto.


def enlace_pago() -> str:
    return os.environ.get("ALIADO_ENLACE_PAGO", "").strip() or "fabian.gulla@gmail.com"


def _nombre() -> str:
    return os.environ.get("ALIADO_NOMBRE", "").strip() or "Aliado Libre"


def planes_activos() -> bool:
    """Los planes de pago solo se ofrecen cuando existen de verdad: ofrecer un
    pase o una membresía que no se pueden comprar es inventar cobertura."""
    return os.environ.get("ALIADO_PLANES_ACTIVOS", "").strip() == "1"


def mensaje_aporte(v: Veredicto) -> str:
    return (
        f"Llevas {v.usadas} consultas hoy. {_nombre()} es gratuito y se sostiene con aportes "
        f"voluntarios: si te está sirviendo, considera apoyarlo ({enlace_pago()}). Puedes seguir "
        f"consultando hasta {v.tope} hoy."
    )


def mensaje_bloqueo(v: Veredicto) -> str:
    if v.vencida:
        return f"Tu membresía venció. Para renovarla: {enlace_pago()}."
    if v.via == "clave":
        cuando = "el primer día del próximo mes" if v.periodo == "mes" else "a medianoche"
        return f"Tu plan llegó a su tope de {v.tope} consultas; se renueva {cuando}. Planes: {enlace_pago()}."
    base = (
        f"Llegaste al límite de {v.tope} consultas gratuitas de hoy; se renueva a medianoche (hora de "
        "Colombia)."
    )
    if planes_activos():
        return (
            f"{base} Si necesitas seguir hoy, puedes comprar un pase de un día, y si consultas seguido, "
            f"una membresía mensual: {enlace_pago()}."
        )
    return f"{base} Si necesitas consultar más para tu trabajo, escríbenos: {enlace_pago()}."


def segundos_hasta_renovar(v: Veredicto, ahora: datetime | None = None) -> int:
    if v.via == "clave" and v.periodo == "mes":
        local = ahora_local(ahora)
        siguiente = (local.replace(day=28) + timedelta(days=4)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return max(1, int((siguiente - local).total_seconds()))
    return segundos_hasta_manana(ahora)
