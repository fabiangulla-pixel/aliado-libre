"""Capa conversacional opcional sobre la búsqueda: toma los fragmentos
recuperados por IndiceBusqueda y le pide a un modelo local (vía Ollama) que
redacte una respuesta en lenguaje natural citándolos — sin esto, Aliado
Libre solo devuelve fragmentos crudos (diseño original del proyecto).

Regla no negociable del proyecto: nunca inventar. El prompt instruye
explícitamente a responder solo con lo que traen los fragmentos y decir
que no hay información suficiente si no alcanza — igual que
`buscar_normativa()` en el servidor MCP."""

from __future__ import annotations

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO_DEFECTO = "gemma3:4b"

PROMPT_SISTEMA = """Eres un asistente que responde preguntas de derecho colombiano \
basándote ÚNICAMENTE en los fragmentos de normas/sentencias/conceptos que se te dan a \
continuación. Reglas estrictas:
- No inventes ni completes con conocimiento propio lo que los fragmentos no digan.
- Si los fragmentos no responden la pregunta, dilo explícitamente: "No encontré \
información suficiente en el índice para responder esto con certeza."
- Cita la fuente de cada afirmación entre paréntesis, ej. (Decreto 1083 de 2015) o \
(Sentencia C-535/1997, Corte Constitucional).
- Responde en español, de forma clara y directa, como lo haría un asistente legal.
"""


def _formatear_fragmentos(resultados: list[dict]) -> str:
    partes = []
    for r in resultados:
        partes.append(
            f"### {r.get('titulo_documento', r.get('identificador_documento', ''))}\n"
            f"Fuente: {r.get('fuente')} | Identificador: {r.get('identificador_documento')}\n"
            f"{r.get('texto', '')}\n"
        )
    return "\n---\n".join(partes)


def responder(consulta: str, resultados: list[dict], modelo: str = MODELO_DEFECTO) -> str:
    """Lanza RuntimeError si Ollama no está corriendo o el modelo no existe —
    el llamador decide si eso es fatal o si debe caer de vuelta a mostrar
    solo los fragmentos crudos."""
    if not resultados:
        return "No encontré información suficiente en el índice para responder esto con certeza."

    contexto = _formatear_fragmentos(resultados)
    prompt = (
        f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}\n\nPregunta: {consulta}\n\nRespuesta:"
    )

    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": modelo, "prompt": prompt, "stream": False},
            timeout=240,
        )
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"No se pudo contactar a Ollama ({OLLAMA_URL}): {e}") from e

    datos = r.json()
    if "error" in datos:
        raise RuntimeError(f"Ollama devolvió un error: {datos['error']}")
    return datos.get("response", "").strip()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from index.buscar import IndiceBusqueda

    consulta = " ".join(sys.argv[1:]) or "requisitos para constituir una fiducia mercantil"
    indice = IndiceBusqueda()
    resultados = indice.buscar(consulta, k=5)
    print(responder(consulta, resultados))
