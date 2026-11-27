"""Pagos con Wompi (Nequi, PSE, Bancolombia, tarjetas): del pago a la clave.

Flujo (docs.wompi.co, leídas el 27-nov-2026):

1. `iniciar(plan)` crea una referencia propia y arma la URL del Web Checkout
   (https://checkout.wompi.co/p/) con su firma de integridad:
   SHA256(referencia + monto_en_centavos + "COP" + secreto_de_integridad).
2. Wompi avisa el resultado por el evento `transaction.updated`. Se verifica su
   checksum: SHA256(valores de `signature.properties` + timestamp + secreto de
   eventos). Un evento que no cuadra se ignora.
3. Con el pago APROBADO, por el monto exacto del plan, se emite una clave
   (`scripts/crear_clave_api.emitir`), se guarda SOLO su hash en el archivo de
   `ALIADO_CLAVES_API` y la cuota del servidor la reconoce al instante.
4. La persona vuelve a `/pago.html?id=<transacción>`; la página pregunta el
   estado (`estado(id)`, que consulta a Wompi con la llave privada: la
   redirección sola no prueba nada) y recibe la clave.

Apagado salvo `ALIADO_PAGOS=wompi`, con las cuatro llaves y con precios. Los
precios NO tienen valor por defecto: los decide Fabián (`ALIADO_PRECIOS_COP`,
p. ej. {"pase-dia": 3500, "mensual": 37000}); un plan sin precio no se ofrece.

Privacidad: aquí no entra ningún dato de quien paga. Wompi los pide y los
guarda (es su trabajo y su política); nosotros guardamos la referencia, el plan,
el monto, el estado y, hasta 24 h, la clave para entregársela.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.request
from pathlib import Path

CHECKOUT = "https://checkout.wompi.co/p/"
API = {"test": "https://sandbox.wompi.co/v1", "prod": "https://production.wompi.co/v1"}
RUTA_PENDIENTES = Path.home() / ".aliado_libre" / "pagos.json"
ARCHIVO_CREDENCIALES = Path.home() / ".aliado_libre" / "credenciales.json"
VIDA_CLAVE_S = 24 * 3600
_lock = threading.Lock()

_CAMPOS = {
    "llave_publica": ("WOMPI_LLAVE_PUBLICA", "wompi_llave_publica"),
    "llave_privada": ("WOMPI_LLAVE_PRIVADA", "wompi_llave_privada"),
    "secreto_integridad": ("WOMPI_SECRETO_INTEGRIDAD", "wompi_secreto_integridad"),
    "secreto_eventos": ("WOMPI_SECRETO_EVENTOS", "wompi_secreto_eventos"),
}


class ErrorPago(RuntimeError):
    pass


def _credencial(nombre: str) -> str:
    """Entorno primero; luego ~/.aliado_libre/credenciales.json (nunca el repo)."""
    var, clave = _CAMPOS[nombre]
    valor = (os.environ.get(var) or "").strip()
    if valor:
        return valor
    try:
        datos = json.loads(ARCHIVO_CREDENCIALES.read_text(encoding="utf-8"))
        return str(datos.get(clave) or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def precios() -> dict[str, int]:
    """Plan -> precio en pesos. Solo planes que existen en crear_clave_api."""
    try:
        crudo = json.loads(os.environ.get("ALIADO_PRECIOS_COP", "") or "{}")
    except ValueError:
        return {}
    try:
        from scripts.crear_clave_api import PLANES
    except ImportError:  # el .exe no lleva scripts/: ahí no se vende nada
        return {}

    return {p: int(v) for p, v in (crudo or {}).items() if p in PLANES and isinstance(v, int) and v > 0}


def ruta_claves() -> Path | None:
    valor = (os.environ.get("ALIADO_CLAVES_API") or "").strip()
    return Path(valor) if valor and not valor.startswith("{") else None


def activo() -> bool:
    return (
        os.environ.get("ALIADO_PAGOS", "").strip() == "wompi"
        and all(_credencial(c) for c in _CAMPOS)
        and bool(precios())
        and ruta_claves() is not None
    )


def ambiente() -> str:
    return "test" if _credencial("llave_publica").startswith("pub_test_") else "prod"


# --- referencias pendientes ---------------------------------------------------


def _leer() -> dict:
    try:
        return json.loads(RUTA_PENDIENTES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _escribir(datos: dict) -> None:
    RUTA_PENDIENTES.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUTA_PENDIENTES.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, RUTA_PENDIENTES)


def _purgar(datos: dict, ahora: float) -> dict:
    """Borra claves en claro vencidas y referencias abandonadas (> 7 días)."""
    for ref, p in list(datos.items()):
        if p.get("clave") and ahora - p.get("emitida_en", ahora) > VIDA_CLAVE_S:
            p.pop("clave", None)
        if p.get("estado") != "APPROVED" and ahora - p.get("creado", ahora) > 7 * 86400:
            datos.pop(ref)
    return datos


# --- 1. iniciar -----------------------------------------------------------------


def firma_integridad(referencia: str, centavos: int, secreto: str) -> str:
    return hashlib.sha256(f"{referencia}{centavos}COP{secreto}".encode()).hexdigest()


def iniciar(plan: str, url_retorno: str, ahora: float | None = None) -> dict:
    tabla = precios()
    if plan not in tabla:
        raise ErrorPago("Ese plan no está a la venta.")
    centavos = tabla[plan] * 100
    referencia = f"AL-{plan}-{secrets.token_hex(8)}"
    with _lock:
        datos = _purgar(_leer(), ahora or time.time())
        datos[referencia] = {
            "plan": plan,
            "centavos": centavos,
            "creado": ahora or time.time(),
            "estado": "PENDING",
        }
        _escribir(datos)
    from urllib.parse import urlencode

    params = {
        "public-key": _credencial("llave_publica"),
        "currency": "COP",
        "amount-in-cents": str(centavos),
        "reference": referencia,
        "signature:integrity": firma_integridad(referencia, centavos, _credencial("secreto_integridad")),
        "redirect-url": url_retorno,
    }
    return {"url": CHECKOUT + "?" + urlencode(params), "referencia": referencia}


# --- 2. eventos -------------------------------------------------------------------


def _valor(datos: dict, ruta: str):
    actual = datos
    for parte in ruta.split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
    return actual


def checksum_valido(evento: dict, cabecera: str | None, secreto: str) -> bool:
    """Pasos de la documentación de eventos de Wompi, al pie de la letra.

    OJO (27-nov-2026): el checksum de ejemplo de esa página (3476DDA5…) NO sale
    de la cadena de ejemplo que ella misma muestra; el ejemplo de la firma de
    integridad sí cuadra. Así que el ejemplo de eventos es ilustrativo y esta
    función no está validada contra un evento real: ANTES de cobrar, hacer un
    pago en sandbox (llaves pub_test_/test_events_) y confirmar que el evento
    pasa. Si no pasara, el servicio no emite claves: falla cerrado."""
    firma = evento.get("signature") or {}
    props = firma.get("properties")
    if not isinstance(props, list) or not props or "timestamp" not in evento:
        return False
    cadena = (
        "".join(str(_valor(evento.get("data") or {}, p)) for p in props) + str(evento["timestamp"]) + secreto
    )
    calculado = hashlib.sha256(cadena.encode()).hexdigest()
    recibido = str(cabecera or firma.get("checksum") or "").lower()
    return hmac.compare_digest(calculado, recibido)


def _emitir_si_corresponde(tx: dict, ahora: float) -> dict | None:
    """Con la transacción aprobada y el monto exacto, emite la clave una sola
    vez por referencia. Devuelve el registro pendiente, o None si no aplica."""
    ref = tx.get("reference")
    with _lock:
        datos = _purgar(_leer(), ahora)
        p = datos.get(ref)
        if p is None:
            return None
        if tx.get("status") != "APPROVED" or tx.get("currency", "COP") != "COP":
            p["estado"] = str(tx.get("status") or p["estado"])
            _escribir(datos)
            return p
        if int(tx.get("amount_in_cents") or -1) != p["centavos"]:
            p["estado"] = "MONTO_DISTINTO"  # nunca se emite por un monto que no es el del plan
            _escribir(datos)
            return p
        if p.get("clave_hash"):
            return p  # ya emitida: los eventos se repiten
        from scripts.crear_clave_api import emitir

        clave, entrada = emitir(p["plan"], f"Wompi {ref}")
        _agregar_clave(entrada)
        h = next(iter(entrada))
        p.update(estado="APPROVED", clave=clave, clave_hash=h, emitida_en=ahora, tx=str(tx.get("id") or ""))
        _escribir(datos)
        return p


def _agregar_clave(entrada: dict) -> None:
    """Hash de la clave al archivo de ALIADO_CLAVES_API y a la cuota en memoria."""
    ruta = ruta_claves()
    if ruta is None:
        raise ErrorPago("ALIADO_CLAVES_API debe apuntar a un archivo para vender claves.")
    try:
        actuales = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    except ValueError:
        raise ErrorPago(f"{ruta} no es JSON válido: no se toca.") from None
    actuales.update(entrada)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(actuales, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ruta)
    from gui import publico
    from servidor_indice.cuotas import _plan_desde_dict

    for h, v in entrada.items():
        plan = _plan_desde_dict(v)
        if plan is not None:
            publico.cuota_busqueda().claves[h] = plan


def procesar_evento(evento: dict, cabecera: str | None, ahora: float | None = None) -> str:
    """Devuelve qué se hizo (para el registro del operador; sin datos personales)."""
    if not checksum_valido(evento, cabecera, _credencial("secreto_eventos")):
        return "checksum inválido: evento ignorado"
    if evento.get("event") != "transaction.updated":
        return "evento sin interés"
    tx = (evento.get("data") or {}).get("transaction") or {}
    p = _emitir_si_corresponde(tx, ahora or time.time())
    return "referencia desconocida" if p is None else f"referencia {tx.get('reference')}: {p['estado']}"


# --- 4. estado ----------------------------------------------------------------------


def consultar_transaccion(tx_id: str) -> dict:
    req = urllib.request.Request(
        f"{API[ambiente()]}/transactions/{tx_id}",
        headers={"Authorization": f"Bearer {_credencial('llave_privada')}"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get("data") or {}


def estado(tx_id: str, ahora: float | None = None) -> dict:
    """Lo que la página de retorno le muestra a la persona."""
    import re

    if not re.fullmatch(r"[\w-]{4,80}", tx_id or ""):
        raise ErrorPago("Identificador de transacción no válido.")
    try:
        tx = consultar_transaccion(tx_id)
    except Exception as e:  # noqa: BLE001
        raise ErrorPago(
            f"No pude consultar el pago en Wompi ({type(e).__name__}). Intenta de nuevo."
        ) from None
    p = _emitir_si_corresponde(tx, ahora or time.time())
    if p is None:
        return {"estado": "desconocido", "mensaje": "Ese pago no corresponde a una compra de este servicio."}
    if p["estado"] == "APPROVED":
        if p.get("clave"):
            return {
                "estado": "aprobado",
                "plan": p["plan"],
                "clave": p["clave"],
                "mensaje": "Pago aprobado. Esta es tu clave: guárdala, la verás solo durante 24 horas.",
            }
        return {"estado": "aprobado", "plan": p["plan"], "mensaje": "Pago aprobado; la clave ya se entregó."}
    if p["estado"] == "PENDING":
        return {
            "estado": "pendiente",
            "mensaje": "El pago está en proceso. Recarga esta página en un minuto.",
        }
    if p["estado"] == "MONTO_DISTINTO":
        return {"estado": "revisar", "mensaje": "El monto pagado no coincide con el del plan. Escríbenos."}
    return {"estado": "rechazado", "mensaje": "El pago no se aprobó. No se te cobró el plan."}
