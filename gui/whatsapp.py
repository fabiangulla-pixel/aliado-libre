"""Canal de WhatsApp (Cloud API de Meta): la persona escribe su problema y
recibe las normas más cercanas, con cita y enlace.

Documentación leída el 27-nov-2026 (developers.facebook.com/docs/whatsapp):

- Verificación del webhook: GET con hub.mode=subscribe, hub.verify_token y
  hub.challenge; se responde 200 con el challenge si el token coincide.
- Cada POST trae `X-Hub-Signature-256: sha256=<HMAC-SHA256(cuerpo, app_secret)>`.
  Se valida sobre los bytes recibidos; si no cuadra, no se procesa.
- Mensaje entrante: entry[].changes[].value.messages[] con from, id, type y
  text.body; metadata.phone_number_id es el número del negocio.
- Respuesta: POST https://graph.facebook.com/<versión>/<phone_number_id>/messages,
  texto de hasta 4096 caracteres.
- Precio: desde el 1-oct-2026 Meta vuelve a cobrar los mensajes de servicio,
  con 1.000 gratis al mes por número. `ALIADO_WA_TOPE_MES` (defecto 1.000)
  corta las respuestas al llegar al cupo gratuito: el servicio no gasta sin
  que Fabián lo decida.

Reglas del proyecto, también aquí:

- **No se guarda nada de la persona.** El número se usa para contestar y se
  descarta; la cuota diaria se cuenta con la huella HMAC de sal diaria de
  `servidor_indice.cuotas`, igual que la IP en la web. Del mes solo se guarda
  un total.
- **Solo búsqueda, sin IA**: responder no cuesta tokens y no inventa. Con
  respaldo débil o ninguno, se dice.
- Se responde 200 enseguida y se trabaja en un hilo: Meta reintenta si tarda,
  y los reintentos duplicarían respuestas (se deduplica por id de mensaje).

Apagado salvo `ALIADO_WHATSAPP=1` con token, app secret y token de verificación.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import urllib.request
from collections import OrderedDict
from pathlib import Path

MAX_TEXTO = 4096
MAX_CONSULTA = 500
RUTA_USO = Path.home() / ".aliado_libre" / "whatsapp_uso.json"
VERSION_DEFECTO = "v27.0"
_vistos: OrderedDict[str, None] = OrderedDict()
_lock = threading.Lock()
_cuota = None


def _env(nombre: str) -> str:
    return (os.environ.get(nombre) or "").strip()


def activo() -> bool:
    return _env("ALIADO_WHATSAPP") == "1" and all(
        _env(v) for v in ("ALIADO_WA_TOKEN", "ALIADO_WA_APP_SECRET", "ALIADO_WA_VERIFY_TOKEN")
    )


def verificar_suscripcion(params: dict) -> str | None:
    """El challenge si la suscripción es válida; None si no."""
    modo = (params.get("hub.mode") or [""])[0]
    token = (params.get("hub.verify_token") or [""])[0]
    reto = (params.get("hub.challenge") or [""])[0]
    if modo == "subscribe" and token and hmac.compare_digest(token, _env("ALIADO_WA_VERIFY_TOKEN")):
        return reto
    return None


def firma_valida(cuerpo: bytes, cabecera: str | None, secreto: str) -> bool:
    if not cabecera or not cabecera.startswith("sha256=") or not secreto:
        return False
    esperado = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecera[len("sha256=") :])


def mensajes_de_texto(evento: dict) -> list[dict]:
    """[{id, de, texto, phone_number_id}] de los mensajes de texto del evento."""
    salida = []
    for entrada in evento.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            valor = cambio.get("value") or {}
            pnid = (valor.get("metadata") or {}).get("phone_number_id")
            for m in valor.get("messages") or []:
                if m.get("type") != "text" or not m.get("from"):
                    continue
                cuerpo = ((m.get("text") or {}).get("body") or "").strip()
                if cuerpo:
                    salida.append(
                        {"id": m.get("id"), "de": m["from"], "texto": cuerpo, "phone_number_id": pnid}
                    )
    return salida


def ya_visto(mensaje_id: str | None) -> bool:
    if not mensaje_id:
        return False
    with _lock:
        if mensaje_id in _vistos:
            return True
        _vistos[mensaje_id] = None
        while len(_vistos) > 5000:
            _vistos.popitem(last=False)
        return False


def _mes() -> str:
    from servidor_indice.cuotas import id_periodo

    return id_periodo("mes")


def _uso_mes() -> int:
    try:
        datos = json.loads(RUTA_USO.read_text(encoding="utf-8"))
        return int(datos.get("enviados", 0)) if datos.get("mes") == _mes() else 0
    except (OSError, ValueError):
        return 0


def _sumar_uso() -> None:
    with _lock:
        n = _uso_mes() + 1
        RUTA_USO.parent.mkdir(parents=True, exist_ok=True)
        tmp = RUTA_USO.with_suffix(".tmp")
        tmp.write_text(json.dumps({"mes": _mes(), "enviados": n}), encoding="utf-8")
        os.replace(tmp, RUTA_USO)


def tope_mes() -> int:
    try:
        return max(0, int(_env("ALIADO_WA_TOPE_MES") or 1000))
    except ValueError:
        return 1000


def cuota_diaria():
    """Mismo contador que la web (huella HMAC con sal diaria), aparte."""
    global _cuota
    with _lock:
        if _cuota is None:
            from servidor_indice.cuotas import Cuotas

            try:
                tope = int(_env("ALIADO_WA_TOPE_DIARIO") or 10)
            except ValueError:
                tope = 10
            _cuota = Cuotas(tope_ip=tope, tope_aporte=None)
        return _cuota


def componer_respuesta(consulta: str, resultados: list[dict], hay_respaldo: bool, url_web: str) -> str:
    """Texto de la respuesta: hasta 3 normas con un extracto y su enlace."""
    lineas = []
    if not resultados:
        lineas.append(
            "No encontré normas en el índice para tu consulta. Intenta contarlo con otras palabras."
        )
    else:
        if not hay_respaldo:
            lineas.append(
                "No encontré una norma que responda esto con claridad. Estos son los textos más cercanos; "
                "léelos solo como pista:"
            )
        else:
            lineas.append("Estas son las normas más cercanas a tu consulta:")
        for i, r in enumerate(resultados[:3], 1):
            extracto = " ".join((r.get("texto") or "").split())[:280]
            linea = f"\n*{i}. {r.get('titulo_documento') or r.get('identificador_documento') or 'Documento'}*"
            v = r.get("vigencia") or {}
            if v.get("alcance") == "documento" and v.get("estado") not in (None, "sin_nota", "incierta"):
                linea += f"\n⚠ Esta norma figura como {v['estado'].upper()}: no rige."
            linea += f"\n«{extracto}…»"
            if r.get("url_original"):
                linea += f"\n{r['url_original']}"
            lineas.append(linea)
    if url_web:
        lineas.append(f"\nPara leer completo, verificar citas o armar un derecho de petición: {url_web}")
    lineas.append("\nOrientación, no asesoría jurídica. No guardamos tus mensajes.")
    return "\n".join(lineas)[:MAX_TEXTO]


def enviar(phone_number_id: str, destino: str, texto: str) -> None:
    version = _env("ALIADO_WA_GRAPH_VERSION") or VERSION_DEFECTO
    cuerpo = json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": destino,
            "type": "text",
            "text": {"preview_url": False, "body": texto[:MAX_TEXTO]},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://graph.facebook.com/{version}/{phone_number_id}/messages",
        data=cuerpo,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_env('ALIADO_WA_TOKEN')}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def atender(mensaje: dict, buscar) -> str | None:
    """Procesa un mensaje y envía la respuesta. `buscar(consulta)` devuelve
    (resultados, hay_respaldo). Devuelve el texto enviado, o None si no se envió
    (duplicado, cupo del mes agotado). Nunca guarda el número."""
    if ya_visto(mensaje.get("id")):
        return None
    if _uso_mes() >= tope_mes():
        return None  # cupo del mes: no se gasta sin decisión del operador
    destino = mensaje["de"]
    v = cuota_diaria().consumir(destino)
    if not v.permitido:
        texto = (
            f"Llegaste al límite de {v.tope} consultas por WhatsApp de hoy; se renueva a medianoche. "
            "En la página web puedes seguir consultando."
        )
    else:
        consulta = mensaje["texto"][:MAX_CONSULTA]
        try:
            resultados, respaldo = buscar(consulta)
        except Exception:  # noqa: BLE001 - un fallo del índice no deja a la persona sin respuesta
            resultados, respaldo = [], False
        texto = componer_respuesta(consulta, resultados, respaldo, _env("ALIADO_URL_PUBLICA"))
    enviar(mensaje["phone_number_id"] or _env("ALIADO_WA_PHONE_NUMBER_ID"), destino, texto)
    _sumar_uso()
    return texto
