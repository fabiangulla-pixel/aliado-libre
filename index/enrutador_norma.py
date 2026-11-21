"""Enrutador de norma: un LLM LOCAL dice que norma regula el caso y, si esa
norma ya esta entre los candidatos de la busqueda, pasa al puesto 1.

Medido el 21-nov-2026 en dev (piloto, 95 preguntas, fusion profunda con
preguntas sinteticas): la norma correcta en el puesto 1 sube de 30.5% a 43.2%
con gemma4:26b. Nunca INYECTA una norma que la busqueda no trajo: medido, en
esos casos el LLM casi siempre se equivoca (1 de 12), y traer un documento que
la busqueda no encontro seria inventar.

Tambien da la CONFIANZA del primer resultado, para que quien muestre la
respuesta decida si afirmarla o presentar opciones:
  "alta"  el LLM y la busqueda coinciden en el puesto 1 (86% de acierto en dev)
  "media" la norma del LLM estaba mas abajo y se subio
  "baja"  el LLM no nombro norma o no estaba entre los candidatos

Apagado por defecto. ALIADO_LLM_NORMA=<modelo de Ollama> lo enciende;
ALIADO_LLM_URL (defecto http://localhost:11434/api/chat) debe ser LOCAL: la
consulta no sale del equipo y Ollama no la guarda. Si el LLM no responde a
tiempo, la busqueda sigue igual (confianza "baja").
"""

from __future__ import annotations

import json
import os
import urllib.request

from index.normas import Norma, norma, norma_de_resultado

MODELO = os.environ.get("ALIADO_LLM_NORMA", "").strip()
URL = os.environ.get("ALIADO_LLM_URL", "http://localhost:11434/api/chat").strip()
TIEMPO = float(os.environ.get("ALIADO_LLM_TIEMPO", "30"))

PROMPT = """Una persona en Colombia pregunta:
"{consulta}"

¿Que ley, decreto o codigo colombiano vigente regula directamente su situacion? Responde SOLO con su nombre y numero, por ejemplo "Ley 1480 de 2011 (Estatuto del Consumidor)" o "Codigo Sustantivo del Trabajo". Si no lo sabes con seguridad, responde "no se"."""  # noqa: E501


def activo() -> bool:
    return bool(MODELO)


def norma_sugerida(consulta: str) -> Norma | None:
    """La norma que nombra el LLM, o None si no nombra ninguna o no responde."""
    if not MODELO:
        return None
    cuerpo = {
        "model": MODELO,
        "messages": [{"role": "user", "content": PROMPT.format(consulta=consulta)}],
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 40, "num_ctx": 1024},
    }
    try:
        req = urllib.request.Request(
            URL, data=json.dumps(cuerpo).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=TIEMPO) as r:
            texto = json.loads(r.read())["message"]["content"]
    except (OSError, ValueError, KeyError):
        return None  # una mejora opcional no puede tumbar la busqueda
    return norma(texto)


def promover(documentos: list[dict], sugerida: Norma | None) -> tuple[list[dict], str]:
    """Sube al puesto 1 el primer documento que ES la norma sugerida.

    `documentos`: un fragmento por documento, en el orden de la busqueda.
    Devuelve (nuevo orden, confianza). No anade nada que no estuviera.
    """
    if sugerida is None:
        return documentos, "baja"
    for i, r in enumerate(documentos):
        if norma_de_resultado(r) == sugerida:
            if i == 0:
                return documentos, "alta"
            return [r] + documentos[:i] + documentos[i + 1 :], "media"
    return documentos, "baja"
