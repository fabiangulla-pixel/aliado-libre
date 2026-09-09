"""De dónde sale la clave de Anthropic para los scripts de evaluación.

Los scripts de `finetune/` exigían `ANTHROPIC_API_KEY` en el entorno. Eso obliga
a exportarla en cada terminal nueva, y lo que pasa en la práctica es que la clave
acaba pegada en un comando del historial, o en un archivo del repositorio. El
proyecto ya tenía resuelto dónde vive un secreto —`~/.aliado_libre/credenciales.json`,
fuera del repositorio, la misma carpeta que lee el .exe para el índice— y aquí se
reutiliza.

Precedencia: el entorno gana sobre el archivo, para que quien depura pueda
sobreescribirla en una terminal sin tocar nada. Ver
index/cliente_remoto.py, que sigue el mismo orden.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ARCHIVO = Path.home() / ".aliado_libre" / "credenciales.json"
CLAVE = "anthropic_api_key"
VARIABLE = "ANTHROPIC_API_KEY"

AYUDA = f"""No hay clave de Anthropic. Dos formas, cualquiera sirve:

  1. Archivo (recomendado, se escribe una vez):
     {ARCHIVO}
     {{"{CLAVE}": "sk-ant-..."}}

  2. Variable de entorno {VARIABLE} en esta terminal.

La clave no debe ir a ningún archivo del repositorio."""


def leer_clave(obligatoria: bool = True) -> str | None:
    """Devuelve la clave, o None si no hay y no es obligatoria.

    Nunca revienta por un archivo corrupto: un JSON mal escrito no puede dejar
    sin clave a quien sí la tiene en el entorno.
    """
    del_entorno = (os.environ.get(VARIABLE) or "").strip()
    if del_entorno:
        return del_entorno
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        if isinstance(datos, dict):
            guardada = str(datos.get(CLAVE) or "").strip()
            if guardada:
                return guardada
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    if obligatoria:
        raise SystemExit(AYUDA)
    return None
