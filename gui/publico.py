"""Modo público de la web: la misma GUI, servida a cualquiera por un túnel.

Decidido el 29-sep-2026 para la beta: el servicio corre en el PC de Fabián y se
expone con Cloudflare Tunnel (sin abrir puertos del router, sin revelar la IP de
la casa, con HTTPS). El servidor sigue escuchando solo en 127.0.0.1: el túnel se
conecta desde dentro.

Qué cambia frente al modo local (`ALIADO_PUBLICO=1`):

- **Cuota de búsqueda** por huella de IP (`servidor_indice/cuotas.py`): aporte
  voluntario sugerido a partir de la consulta 16, bloqueo a partir de la 31.
- **Redacción con IA**: la hace la nube con la clave del SERVIDOR, no el modelo
  local; como cada respuesta cuesta dinero, hay **3 gratis al día** por huella y
  un **tope de gasto mensual** (`ALIADO_TOPE_GASTO_MES_USD`). Pasado el tope, la
  búsqueda con citas sigue funcionando.
- Sin modelo local ni navegador que se abra solo.

Privacidad, igual que el servidor del índice: la IP nunca se guarda (huella HMAC
con sal diaria en memoria) y del gasto solo se guarda el total del mes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

NOMBRE_DEFECTO = "Juris-consulta ColombIA"
REDACCIONES_DIARIAS_DEFECTO = 3
TOPE_GASTO_MES_DEFECTO = 10.0
RUTA_GASTO = Path.home() / ".aliado_libre" / "gasto_publico.json"


def activo() -> bool:
    return os.environ.get("ALIADO_PUBLICO", "").strip() == "1"


def nombre_producto() -> str:
    return os.environ.get("ALIADO_NOMBRE", "").strip() or NOMBRE_DEFECTO


def _entero(var: str, defecto: int) -> int:
    try:
        return max(0, int(os.environ.get(var, defecto)))
    except ValueError:
        return defecto


def ip_cliente(handler) -> str:
    """Detrás de Cloudflare Tunnel todas las peticiones llegan desde 127.0.0.1;
    la IP real viene en `CF-Connecting-IP`. Solo se cree con
    ALIADO_CONFIAR_PROXY=1: sin túnel, cualquiera podría falsearla y regalarse
    cuota infinita."""
    if os.environ.get("ALIADO_CONFIAR_PROXY", "").strip() == "1":
        for cabecera in ("CF-Connecting-IP", "X-Forwarded-For"):
            valor = handler.headers.get(cabecera, "").split(",")[0].strip()
            if valor:
                return valor
    return handler.client_address[0]


# --- cuotas -----------------------------------------------------------------

_lock = threading.Lock()
_cuota_busqueda = None
_cuota_redaccion = None


def cuota_busqueda():
    global _cuota_busqueda
    with _lock:
        if _cuota_busqueda is None:
            from servidor_indice.cuotas import Cuotas

            _cuota_busqueda = Cuotas.desde_entorno()
        return _cuota_busqueda


def cuota_redaccion():
    global _cuota_redaccion
    with _lock:
        if _cuota_redaccion is None:
            from servidor_indice.cuotas import Cuotas

            _cuota_redaccion = Cuotas(
                tope_ip=_entero("ALIADO_REDACCIONES_DIARIAS", REDACCIONES_DIARIAS_DEFECTO), tope_aporte=None
            )
        return _cuota_redaccion


def reiniciar() -> None:
    """Para las pruebas."""
    global _cuota_busqueda, _cuota_redaccion
    with _lock:
        _cuota_busqueda = _cuota_redaccion = None


# --- tope de gasto mensual ---------------------------------------------------


class Presupuesto:
    """Lleva el gasto de IA del mes. Solo un total: nada de quién lo gastó."""

    def __init__(self, tope_usd: float, ruta: Path = RUTA_GASTO):
        self.tope_usd = tope_usd
        self.ruta = ruta
        self._lock = threading.Lock()

    @classmethod
    def desde_entorno(cls) -> Presupuesto:
        try:
            tope = float(os.environ.get("ALIADO_TOPE_GASTO_MES_USD", TOPE_GASTO_MES_DEFECTO))
        except ValueError:
            tope = TOPE_GASTO_MES_DEFECTO
        return cls(max(0.0, tope))

    def _leer(self, mes: str) -> float:
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            return float(datos.get("usd", 0.0)) if datos.get("mes") == mes else 0.0
        except (OSError, ValueError, AttributeError):
            return 0.0

    def gastado(self, mes: str) -> float:
        with self._lock:
            return self._leer(mes)

    def queda(self, mes: str) -> bool:
        return self.gastado(mes) < self.tope_usd

    def registrar(self, mes: str, usd: float) -> None:
        with self._lock:
            total = self._leer(mes) + max(0.0, usd)
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal = self.ruta.with_suffix(".tmp")
            temporal.write_text(json.dumps({"mes": mes, "usd": round(total, 6)}), encoding="utf-8")
            os.replace(temporal, self.ruta)


_presupuesto = None


def presupuesto() -> Presupuesto:
    global _presupuesto
    with _lock:
        if _presupuesto is None:
            _presupuesto = Presupuesto.desde_entorno()
        return _presupuesto


def mes_actual() -> str:
    from servidor_indice.cuotas import id_periodo

    return id_periodo("mes")


# --- redacción por nube con la clave del servidor ----------------------------


def redactar(consulta: str, fragmentos: list[dict]) -> tuple[str, float]:
    """(texto, costo en USD). Lanza RuntimeError si no hay clave o falla."""
    from finetune.clave_api import leer_clave
    from index import costos
    from index.proveedores import MODELOS_POR_DEFECTO, ErrorProveedor, generar
    from index.responder import PROMPT_SISTEMA, _formatear_fragmentos

    clave = leer_clave(obligatoria=False) or ""
    if not clave:
        raise RuntimeError("El servidor no tiene configurada la clave de IA.")
    modelo = MODELOS_POR_DEFECTO["claude"]
    contexto = _formatear_fragmentos(fragmentos)
    prompt = f"Fragmentos disponibles:\n\n{contexto}\n\nPregunta: {consulta}\n\nRespuesta:"
    try:
        r = generar(prompt, PROMPT_SISTEMA, "claude", clave=clave, modelo=modelo)
    except ErrorProveedor as e:
        raise RuntimeError(f"La IA no respondió: {e}") from None
    return r.texto, costos.liquidar(r.usage, r.modelo).usd
