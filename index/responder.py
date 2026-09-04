"""Capa conversacional opcional sobre la búsqueda: toma los fragmentos
recuperados por el índice (local o remoto) y le pide al modelo propio
—Qwen2.5-1.5B afinado, cuantizado a GGUF Q4_K_M— que redacte una respuesta
en lenguaje natural citándolos. Sin esto, Aliado Libre solo devuelve
fragmentos crudos (diseño original del proyecto).

El motor de inferencia es ``llama_cpp.Llama``, **en proceso**: el modelo se
carga desde un archivo .gguf que viaja al lado del .exe.

Qué pasó con Ollama
-------------------
Se **eliminó**. Antes este módulo hablaba por HTTP con Ollama en
``localhost:11434``, lo que obligaba al usuario final a instalar y arrancar
Ollama aparte: era el último motivo por el que el .exe no era autónomo.
Además, el modelo que se sirve aquí es el propio (el ganador de la
comparación de 4 modelos), no un modelo genérico del catálogo de Ollama, así
que el camino alternativo no aportaba calidad sino una segunda ruta de
código que nadie mediría. Quien quiera usar otro modelo puede apuntar
``ALIADO_MODELO_GGUF`` a otro .gguf.

Regla no negociable del proyecto: nunca inventar. El prompt instruye
explícitamente a responder solo con lo que traen los fragmentos y decir
que no hay información suficiente si no alcanza — igual que
`buscar_normativa()` en el servidor MCP."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

# --- parámetros de inferencia -------------------------------------------
# Son EXACTAMENTE los que se usaron para medir la calidad del modelo
# (finetune/generar_respuestas_local.py y finetune/colab_evaluar_gpu.ipynb).
# El 38% de acierto que ganó la comparación de 4 modelos se midió con estos
# valores: si producción usa otros, ese número deja de decir nada sobre lo
# que el usuario recibe. No cambiar sin volver a correr la evaluación.
N_CTX = 8192
MAX_TOKENS = 400
TEMPERATURA = 0.2
STOPS = ["Pregunta:", "###"]

NOMBRE_GGUF = "modelo_lora_15b.q4_k_m.gguf"
VAR_MODELO = "ALIADO_MODELO_GGUF"

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

_modelo = None
_modelo_lock = threading.Lock()


def _carpeta_modelo_congelado() -> Path:
    """Junto al .exe (NO ``sys._MEIPASS``): el GGUF se distribuye al lado del
    ejecutable, en ``modelo/``, porque onefile descomprime su contenido en
    cada arranque y ~1 GB de pesos haría eso inviable."""
    return Path(sys.executable).resolve().parent / "modelo"


def ruta_modelo() -> Path:
    """Ruta del .gguf en los dos mundos: congelado (``modelo/`` junto al .exe)
    y desarrollo (``finetune/salida/``). ``ALIADO_MODELO_GGUF`` manda sobre
    ambos y puede apuntar a un archivo o a una carpeta que lo contenga."""
    sobrescrito = os.environ.get(VAR_MODELO, "").strip()
    if sobrescrito:
        ruta = Path(sobrescrito).expanduser()
        return ruta / NOMBRE_GGUF if ruta.is_dir() else ruta

    if getattr(sys, "frozen", False):
        return _carpeta_modelo_congelado() / NOMBRE_GGUF
    return Path(__file__).resolve().parent.parent / "finetune" / "salida" / NOMBRE_GGUF


def _mensaje_falta_modelo(ruta: Path) -> str:
    return (
        f"No encontré el modelo de lenguaje: falta el archivo «{NOMBRE_GGUF}» en "
        f"{ruta.parent}. Copia ahí el archivo (o indica su ubicación en la variable "
        f"de entorno {VAR_MODELO}) y vuelve a intentarlo. Mientras tanto, Aliado "
        "Libre sigue funcionando como buscador y te muestra los fragmentos citados."
    )


def cargar_modelo():
    """Carga perezosa y única del GGUF (940 MB: cargarlo por consulta sería
    inaceptable). Lanza RuntimeError con un mensaje en español si falta el
    archivo, si llama-cpp-python no está instalado o si la carga falla."""
    global _modelo
    if _modelo is not None:
        return _modelo
    with _modelo_lock:
        if _modelo is not None:
            return _modelo

        ruta = ruta_modelo()
        if not ruta.is_file():
            raise RuntimeError(_mensaje_falta_modelo(ruta))

        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise RuntimeError(
                "Falta el motor de inferencia llama-cpp-python en esta instalación: "
                f"no se puede cargar {ruta}. ({e})"
            ) from e

        try:
            _modelo = Llama(model_path=str(ruta), n_ctx=N_CTX, verbose=False)
        except Exception as e:
            raise RuntimeError(
                f"No se pudo cargar el modelo de lenguaje en {ruta}: {e}. "
                "Puede estar incompleto o corrupto; vuelve a copiarlo."
            ) from e
        return _modelo


def _formatear_fragmentos(resultados: list[dict]) -> str:
    partes = []
    for r in resultados:
        partes.append(
            f"### {r.get('titulo_documento', r.get('identificador_documento', ''))}\n"
            f"Fuente: {r.get('fuente')} | Identificador: {r.get('identificador_documento')}\n"
            f"{r.get('texto', '')}\n"
        )
    return "\n---\n".join(partes)


def construir_prompt(consulta: str, resultados: list[dict]) -> str:
    contexto = _formatear_fragmentos(resultados)
    return f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}\n\nPregunta: {consulta}\n\nRespuesta:"


def responder(consulta: str, resultados: list[dict]) -> str:
    """Lanza RuntimeError si el modelo no está disponible o falla la
    inferencia — el llamador decide si eso es fatal o si debe caer de vuelta
    a mostrar solo los fragmentos crudos (que es lo que hace la GUI)."""
    if not resultados:
        return "No encontré información suficiente en el índice para responder esto con certeza."

    modelo = cargar_modelo()
    prompt = construir_prompt(consulta, resultados)

    try:
        salida = modelo(prompt, max_tokens=MAX_TOKENS, temperature=TEMPERATURA, stop=STOPS)
    except Exception as e:
        raise RuntimeError(f"El modelo de lenguaje falló al responder: {e}") from e

    return salida["choices"][0]["text"].strip()


if __name__ == "__main__":
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from index.buscar import IndiceBusqueda

    consulta = " ".join(sys.argv[1:]) or "requisitos para constituir una fiducia mercantil"
    indice = IndiceBusqueda()
    resultados = indice.buscar(consulta, k=5)
    print(responder(consulta, resultados))
