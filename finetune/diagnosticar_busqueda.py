"""Diagnóstico del hallazgo del 41% de fallo de recuperación: para un lote de
preguntas nuevas generadas desde fragmentos reales, mide en qué falla el
buscador — ¿el embedding no encuentra el fragmento ni en un top grande?
¿BM25 sí lo encuentra pero la fusión RRF lo hunde? ¿el fragmento aparece
pero fuera del top-5 final por poco?

Esto separa el diagnóstico en 3 posibles causas con arreglos muy distintos:
- Si BM25 solo SÍ encuentra el documento pero el vectorial no: el modelo de
  embeddings (paraphrase-multilingual-MiniLM-L12-v2, genérico y liviano) no
  entiende bien el vocabulario legal/histórico — subir K_RRF o el peso de
  BM25 ayuda, o cambiar de modelo de embeddings.
- Si NINGUNO de los dos lo encuentra ni en un top-50 amplio: el problema es
  más profundo (el fragmento es demasiado corto/genérico, o la pregunta
  generada por el LLM no se parece al contenido real).
- Si SÍ aparece pero fuera del top-5 final (ej. puesto 6-15): basta con subir
  k en producción, no hay que tocar el algoritmo.

Requiere ANTHROPIC_API_KEY.

Uso:
    ./venv/Scripts/python.exe finetune/diagnosticar_busqueda.py [n]
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finetune.generar_dataset_ampliado import _generar_pregunta_respuesta, _muestrear_fragmentos
from index.buscar import IndiceBusqueda, _tokenizar

RAIZ = Path(__file__).resolve().parent


def main() -> None:
    import anthropic

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")
    cliente = anthropic.Anthropic(api_key=api_key)

    print("Cargando índice (una vez)...")
    indice = IndiceBusqueda()

    print(f"Muestreando {n + 15} fragmentos y generando preguntas...")
    fragmentos = _muestrear_fragmentos(n + 15, semilla=31415)
    rng = random.Random(1)
    rng.shuffle(fragmentos)

    casos = []
    for frag in fragmentos:
        if len(casos) >= n:
            break
        resultado = _generar_pregunta_respuesta(cliente, frag)
        if resultado is None:
            continue
        pregunta, _respuesta, _tin, _tout = resultado
        casos.append((frag, pregunta))

    print(f"\nDiagnosticando {len(casos)} casos...\n")

    solo_bm25 = 0
    solo_vector = 0
    ninguno_top50 = 0
    fuera_de_top5_por_poco = 0
    encontrado_top5 = 0

    for frag, pregunta in casos:
        objetivo = frag["identificador_documento"]

        embedding_consulta = indice._modelo.encode([pregunta]).tolist()
        resultado_vectorial = indice._coleccion.query(query_embeddings=embedding_consulta, n_results=50)
        ids_vectorial = resultado_vectorial["ids"][0]

        puntajes_bm25 = indice._bm25.get_scores(_tokenizar(pregunta))
        orden_bm25 = sorted(range(len(indice._ids)), key=lambda i: puntajes_bm25[i], reverse=True)[:50]
        ids_bm25 = [indice._ids[i] for i in orden_bm25]

        # mapear chroma ids -> identificador_documento para comparar
        id_a_doc = {
            indice._ids[j]: indice._metadatas[j].get("identificador_documento")
            for j in range(len(indice._ids))
        }

        rank_vector = next((i for i, cid in enumerate(ids_vectorial) if id_a_doc.get(cid) == objetivo), None)
        rank_bm25 = next((i for i, cid in enumerate(ids_bm25) if id_a_doc.get(cid) == objetivo), None)

        resultados_reales_k5 = indice.buscar(pregunta, k=5)
        en_top5 = any(r.get("identificador_documento") == objetivo for r in resultados_reales_k5)

        if en_top5:
            encontrado_top5 += 1
            categoria = "OK top-5"
        elif rank_vector is not None or rank_bm25 is not None:
            fuera_de_top5_por_poco += 1
            categoria = (
                f"cerca (vector rank={rank_vector}, bm25 rank={rank_bm25}) pero no llegó al top-5 fusionado"
            )
        else:
            ninguno_top50 += 1
            categoria = "NO aparece ni en top-50 de ninguno de los dos métodos"

        if rank_bm25 is not None and rank_vector is None:
            solo_bm25 += 1
        elif rank_vector is not None and rank_bm25 is None:
            solo_vector += 1

        print(f"- [{objetivo}] {pregunta[:70]}")
        print(f"    {categoria}")

    print("\n" + "=" * 60)
    print(f"Total casos: {len(casos)}")
    print(f"  Encontrados en el top-5 real: {encontrado_top5} ({encontrado_top5 / len(casos) * 100:.0f}%)")
    print(f"  Aparecen en top-50 de alguno pero no llegan al top-5 fusionado: {fuera_de_top5_por_poco}")
    print(f"  No aparecen NI en top-50 de vector NI de BM25: {ninguno_top50}")
    print(f"  (de los que sí aparecen en algún método) solo BM25 los encuentra: {solo_bm25}")
    print(f"  (de los que sí aparecen en algún método) solo el vectorial los encuentra: {solo_vector}")


if __name__ == "__main__":
    main()
