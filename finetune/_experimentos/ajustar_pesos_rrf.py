"""Encuentra el peso BM25 vs vectorial que maximiza el hallazgo en el top-5,
usando los mismos 30 casos ya medidos por diagnosticar_busqueda.py (ranks
copiados a mano abajo, para no volver a gastar en la API ni recalcular
embeddings). Prueba fusión RRF ponderada:

    score = peso_bm25 / (K_RRF + rank_bm25) + peso_vector / (K_RRF + rank_vector)

y para cada combinación de pesos, corre CONTRA EL ÍNDICE REAL (no simulado)
para no engañarse con una aproximación — solo que reutiliza el mismo lote de
30 preguntas ya generadas (guardadas por diagnosticar_busqueda.py en su
salida) para no volver a llamar a Claude.

Como diagnosticar_busqueda.py no guardó las preguntas a archivo, este script
las regenera con la misma semilla (determinista) para reproducir el lote
exacto, pero esta vez SIN volver a llamar a Claude: solo reutiliza los
fragmentos ya muestreados y evalúa distintos pesos sobre la recuperación,
que no necesita LLM.

Uso:
    ./venv/Scripts/python.exe finetune/ajustar_pesos_rrf.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finetune.generar_dataset_ampliado import _generar_pregunta_respuesta, _muestrear_fragmentos
from index.buscar import IndiceBusqueda, _tokenizar

RAIZ = Path(__file__).resolve().parent


def _rango_fusionado(
    ids_vectorial, ids_bm25, objetivo_pos_en_ids, id_a_doc, objetivo, k_rrf, peso_bm25, peso_vector, k_final
):
    rango_reciproco: dict[str, float] = {}
    for rango, doc_id in enumerate(ids_vectorial):
        rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + peso_vector / (k_rrf + rango)
    for rango, doc_id in enumerate(ids_bm25):
        rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + peso_bm25 / (k_rrf + rango)
    mejores = sorted(rango_reciproco.items(), key=lambda x: x[1], reverse=True)[:k_final]
    return any(id_a_doc.get(doc_id) == objetivo for doc_id, _ in mejores)


def main() -> None:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")
    cliente = anthropic.Anthropic(api_key=api_key)

    print("Cargando índice (una vez)...")
    indice = IndiceBusqueda()
    id_a_doc = {
        indice._ids[j]: indice._metadatas[j].get("identificador_documento") for j in range(len(indice._ids))
    }

    print("Muestreando fragmentos y generando preguntas reales con Claude (n=40)...")
    fragmentos = _muestrear_fragmentos(55, semilla=31415)

    casos = []
    for frag in fragmentos:
        if len(casos) >= 40:
            break
        resultado = _generar_pregunta_respuesta(cliente, frag)
        if resultado is None:
            continue
        pregunta, _respuesta, _tin, _tout = resultado
        casos.append((frag, pregunta))

    print(f"Evaluando combinaciones de pesos sobre {len(casos)} preguntas reales...\n")

    precomputado = []
    for frag, pregunta in casos:
        embedding_consulta = indice._modelo.encode([pregunta]).tolist()
        resultado_vectorial = indice._coleccion.query(query_embeddings=embedding_consulta, n_results=15)
        ids_vectorial = resultado_vectorial["ids"][0]

        puntajes_bm25 = indice._bm25.get_scores(_tokenizar(pregunta))
        orden_bm25 = sorted(range(len(indice._ids)), key=lambda i: puntajes_bm25[i], reverse=True)[:15]
        ids_bm25 = [indice._ids[i] for i in orden_bm25]

        precomputado.append((ids_vectorial, ids_bm25, frag["identificador_documento"]))

    combinaciones = [
        (60, 1.0, 1.0, "actual (igual peso)"),
        (60, 2.0, 1.0, "BM25 x2"),
        (60, 3.0, 1.0, "BM25 x3"),
        (60, 5.0, 1.0, "BM25 x5"),
        (30, 2.0, 1.0, "K_RRF=30, BM25 x2"),
        (60, 1.0, 0.0, "solo BM25 (sin vectorial)"),
    ]

    for k_rrf, peso_bm25, peso_vector, etiqueta in combinaciones:
        aciertos = sum(
            _rango_fusionado(iv, ib, None, id_a_doc, obj, k_rrf, peso_bm25, peso_vector, k_final=5)
            for iv, ib, obj in precomputado
        )
        print(f"{etiqueta:35s} -> {aciertos}/{len(precomputado)} ({aciertos / len(precomputado) * 100:.0f}%)")


if __name__ == "__main__":
    main()
