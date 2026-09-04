"""Prueba rápida de un modelo GGUF exportado: carga con llama-cpp-python y le
hace una pregunta real usando fragmentos reales del índice de Aliado Libre,
con el mismo PROMPT_SISTEMA que usa index/responder.py — para comparar
la calidad del modelo fine-tuneado contra gemma3:4b/phi4-mini genéricos.

Uso:
    ./venv/Scripts/python.exe finetune/probar_gguf.py finetune/salida/modelo_lora_05b.q8_0.gguf "pregunta"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from index.buscar import IndiceBusqueda
from index.responder import PROMPT_SISTEMA, _formatear_fragmentos


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Uso: probar_gguf.py <ruta.gguf> [pregunta]")
    ruta_gguf = sys.argv[1]
    consulta = " ".join(sys.argv[2:]) or "requisitos para constituir una fiducia mercantil"

    from llama_cpp import Llama

    print(f"Cargando {ruta_gguf}...")
    modelo = Llama(model_path=ruta_gguf, n_ctx=8192, verbose=False)

    print(f"Buscando fragmentos para: {consulta!r}")
    indice = IndiceBusqueda()
    resultados = indice.buscar(consulta, k=5)
    if not resultados:
        print("Sin resultados en el índice para esta consulta.")
        return

    contexto = _formatear_fragmentos(resultados)
    prompt = (
        f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}\n\nPregunta: {consulta}\n\nRespuesta:"
    )

    print("Generando respuesta...\n" + "-" * 60)
    salida = modelo(prompt, max_tokens=400, temperature=0.2, stop=["Pregunta:", "###"])
    print(salida["choices"][0]["text"].strip())


if __name__ == "__main__":
    main()
