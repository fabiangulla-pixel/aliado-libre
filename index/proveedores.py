"""Despacho a proveedores de IA con clave puesta por el usuario.

Sigue el patrón de `core/inference_provider.py` de Bashkar Station: una capa
única de despacho, `RespuestaProveedor` con texto y `usage` crudo para poder
contabilizar el costo, e importación perezosa del SDK dentro de cada rama (así
el .exe no arrastra SDKs que quizá nadie use, y los tests pueden sustituirlos).

Dos reglas propias de este proyecto, y no son negociables:

1. **La clave no se guarda.** Llega como parámetro en la llamada, vive en
   memoria mientras dura la petición y se descarta. No se escribe a disco, no
   va a variables de entorno del servidor, no se registra. Si algún día hay
   versión con perfil de usuario que la recuerde, será una decisión explícita
   y separada, no una consecuencia de este archivo.
2. **La clave nunca aparece en un mensaje de error.** Los SDK a veces incluyen
   la cabecera de autorización en la excepción; `_limpiar` la borra antes de
   que el texto salga de aquí.

El modelo propio (GGUF local) no está aquí: vive en `index/responder.py` y no
necesita clave. Qué consulta va a cuál lo decide `index/enrutador.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_TOKENS = 700
TEMPERATURA = 0.2

# Modelo por defecto de cada proveedor. Se puede sobrescribir por llamada.
MODELOS_POR_DEFECTO = {
    "claude": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.1",
}

PROVEEDORES = tuple(MODELOS_POR_DEFECTO)

# Proveedores que corren en la máquina del usuario y por eso no piden clave.
SIN_CLAVE = frozenset({"ollama"})

_PATRONES_CLAVE = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(authorization|x-api-key|api[_-]?key)\s*[:=]\s*\S+"),
)


@dataclass
class RespuestaProveedor:
    texto: str
    usage: object | None = None
    proveedor: str = ""
    modelo: str = ""


class ErrorProveedor(RuntimeError):
    """Fallo al hablar con un proveedor, ya con la clave borrada del mensaje."""


def _limpiar(texto: str) -> str:
    """Borra cualquier cosa con forma de clave del texto de un error."""
    for patron in _PATRONES_CLAVE:
        texto = patron.sub("[clave omitida]", texto)
    return texto


def _acepta_temperatura(metodo) -> bool:
    """¿Este SDK todavía recibe `temperature` en messages.create?

    El SDK de Anthropic lo retiró de la firma (verificado con 1.3.0, que en su
    lugar expone `output_config` con `effort` y `format`). Pasarlo levanta
    TypeError y **toda** la ruta de respuesta por nube queda caída, que es como
    estaba el 12-sep-2026: las 100 consultas del piloto fallaron con
    "Messages.create() got an unexpected keyword argument 'temperature'".
    Se consulta la firma en vez de fijar una versión, para que el programa
    funcione con el SDK que el usuario tenga instalado.
    """
    import inspect

    try:
        parametros = inspect.signature(metodo).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parametros.values()):
        return True
    return "temperature" in parametros


def _claude(prompt: str, sistema: str, clave: str, modelo: str) -> RespuestaProveedor:
    import anthropic

    cliente = anthropic.Anthropic(api_key=clave)
    extra = {"temperature": TEMPERATURA} if _acepta_temperatura(cliente.messages.create) else {}
    msg = cliente.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        system=sistema,
        messages=[{"role": "user", "content": prompt}],
        **extra,
    )
    # Con thinking adaptativo el primer bloque puede no ser texto: hay que
    # buscar el bloque de tipo "text" en vez de asumir content[0].
    for bloque in msg.content:
        if getattr(bloque, "type", None) == "text":
            return RespuestaProveedor(bloque.text.strip(), msg.usage, "claude", modelo)
    raise ErrorProveedor(
        f"Respuesta de Claude sin bloque de texto (stop_reason={getattr(msg, 'stop_reason', None)!r})"
    )


def _openai(prompt: str, sistema: str, clave: str, modelo: str) -> RespuestaProveedor:
    from openai import OpenAI

    cliente = OpenAI(api_key=clave)
    r = cliente.chat.completions.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURA,
        messages=[
            {"role": "system", "content": sistema},
            {"role": "user", "content": prompt},
        ],
    )
    return RespuestaProveedor(r.choices[0].message.content.strip(), r.usage, "openai", modelo)


def _gemini(prompt: str, sistema: str, clave: str, modelo: str) -> RespuestaProveedor:
    import google.generativeai as genai

    genai.configure(api_key=clave)
    m = genai.GenerativeModel(modelo, system_instruction=sistema)
    r = m.generate_content(
        prompt,
        generation_config={"max_output_tokens": MAX_TOKENS, "temperature": TEMPERATURA},
    )
    return RespuestaProveedor(r.text.strip(), getattr(r, "usage_metadata", None), "gemini", modelo)


def _ollama(prompt: str, sistema: str, clave: str, modelo: str) -> RespuestaProveedor:
    """Servidor local del propio usuario: no lleva clave."""
    import json
    import urllib.request

    cuerpo = json.dumps(
        {
            "model": modelo,
            "prompt": prompt,
            "system": sistema,
            "stream": False,
            "options": {"temperature": TEMPERATURA, "num_predict": MAX_TOKENS},
        }
    ).encode("utf-8")
    peticion = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=cuerpo,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion, timeout=180) as r:
        datos = json.loads(r.read().decode("utf-8"))
    return RespuestaProveedor(datos.get("response", "").strip(), None, "ollama", modelo)


# Se guardan NOMBRES y no funciones: así la función se resuelve en el momento
# de la llamada y un test puede sustituir `_claude` con monkeypatch sin tener
# que conocer esta tabla. Mismo criterio que en Bashkar Station.
_DESPACHO = {
    "claude": "_claude",
    "openai": "_openai",
    "gemini": "_gemini",
    "ollama": "_ollama",
}


def _funcion(proveedor: str):
    return globals()[_DESPACHO[proveedor]]


def generar(
    prompt: str,
    sistema: str,
    proveedor: str,
    clave: str | None = None,
    modelo: str | None = None,
) -> RespuestaProveedor:
    """Pide una respuesta al proveedor indicado con la clave que da el usuario.

    `clave` no se guarda en ninguna parte: se usa para construir el cliente y
    se descarta al terminar la llamada.
    """
    proveedor = (proveedor or "").strip().lower()
    if proveedor not in _DESPACHO:
        raise ErrorProveedor(f"Proveedor desconocido: {proveedor!r}. Disponibles: {', '.join(PROVEEDORES)}.")
    if proveedor not in SIN_CLAVE and not (clave or "").strip():
        raise ErrorProveedor(
            f"Falta la clave de API para {proveedor}. La pones tú y no se guarda en ningún lado."
        )

    modelo = modelo or MODELOS_POR_DEFECTO[proveedor]
    try:
        return _funcion(proveedor)(prompt, sistema, (clave or "").strip(), modelo)
    except ErrorProveedor:
        raise
    except ImportError as e:
        raise ErrorProveedor(f"Falta instalar el SDK de {proveedor}: {_limpiar(str(e))}") from None
    except Exception as e:
        # Sin encadenar la excepción original: su traza puede llevar la clave
        # en una cabecera de la petición.
        raise ErrorProveedor(f"{proveedor} falló ({type(e).__name__}): {_limpiar(str(e))}") from None
