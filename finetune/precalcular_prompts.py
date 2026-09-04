"""Precalcula, para el banco de prueba ya generado (finetune/eval/banco_prueba.json),
el prompt completo (con los 5 fragmentos reales que trae la búsqueda) para cada
pregunta — así Colab no necesita el índice completo (Chroma 9.2GB + FTS5 1.5GB,
demasiado pesado para subir) para generar las respuestas con GPU. Solo necesita
este archivo chico + los .gguf.

El juicio (comparar respuesta vs fragmentos con Claude) se hace aparte, local,
después de bajar las respuestas de Colab — eso no necesita GPU, es solo
llamadas a la API, misma velocidad en cualquier lado.

Uso:
    ./venv/Scripts/python.exe finetune/precalcular_prompts.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from index.buscar import IndiceBusqueda
from index.responder import PROMPT_SISTEMA, _formatear_fragmentos

RAIZ = Path(__file__).resolve().parent


def main() -> None:
    banco = json.loads((RAIZ / "eval" / "banco_prueba.json").read_text(encoding="utf-8"))
    print(f"{len(banco)} preguntas en el banco de prueba.")

    print("Cargando índice de búsqueda...")
    indice = IndiceBusqueda()

    precalculados = []
    for i, caso in enumerate(banco, 1):
        resultados = indice.buscar(caso["pregunta"], k=5)
        if resultados:
            contexto = _formatear_fragmentos(resultados)
            prompt = (
                f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}"
                f"\n\nPregunta: {caso['pregunta']}\n\nRespuesta:"
            )
        else:
            prompt = None
        precalculados.append(
            {
                "pregunta": caso["pregunta"],
                "respuesta_esperada": caso["respuesta_esperada"],
                "es_negativo": caso["es_negativo"],
                "prompt": prompt,
                "fragmentos": resultados,
            }
        )
        if i % 30 == 0:
            print(f"  {i}/{len(banco)}")

    salida = RAIZ / "eval" / "prompts_precalculados.json"
    salida.write_text(json.dumps(precalculados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(precalculados)} prompts precalculados escritos en {salida}")


if __name__ == "__main__":
    main()
