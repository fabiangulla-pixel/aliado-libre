"""Búsqueda híbrida sobre el índice: vectorial (Chroma) + léxica (BM25) con
fusión por rango recíproco (RRF), como en ReactivosFlow. La búsqueda léxica
importa para citas exactas (números de ley, artículos) que los embeddings
por sí solos suelen perder."""

from __future__ import annotations

import re
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"
DIR_INDICE = Path(__file__).resolve().parent / "chroma_db"
COLECCION = "aliado_libre"
K_RRF = 60


def _tokenizar(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


class IndiceBusqueda:
    def __init__(self) -> None:
        self._modelo = SentenceTransformer(MODELO_EMBEDDINGS)
        self._cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
        self._coleccion = self._cliente.get_or_create_collection(COLECCION)

        # .get() sin límite genera una consulta SQL con demasiadas variables
        # para corpus grandes ("too many SQL variables") -> se pagina.
        self._ids: list[str] = []
        self._textos: list[str] = []
        self._metadatas: list[dict] = []
        tamanio_lote = 5000
        offset = 0
        while True:
            lote = self._coleccion.get(include=["documents", "metadatas"], limit=tamanio_lote, offset=offset)
            if not lote["ids"]:
                break
            self._ids.extend(lote["ids"])
            self._textos.extend(lote["documents"])
            self._metadatas.extend(lote["metadatas"])
            offset += len(lote["ids"])
        self._bm25 = BM25Okapi([_tokenizar(t) for t in self._textos]) if self._textos else None

    def buscar(self, consulta: str, k: int = 8) -> list[dict]:
        if not self._ids:
            return []

        embedding_consulta = self._modelo.encode([consulta]).tolist()
        resultado_vectorial = self._coleccion.query(
            query_embeddings=embedding_consulta, n_results=min(k * 3, len(self._ids))
        )
        ids_vectorial = resultado_vectorial["ids"][0]

        puntajes_bm25 = self._bm25.get_scores(_tokenizar(consulta))
        orden_bm25 = sorted(range(len(self._ids)), key=lambda i: puntajes_bm25[i], reverse=True)
        ids_bm25 = [self._ids[i] for i in orden_bm25[: k * 3]]

        rango_reciproco: dict[str, float] = {}
        for rango, doc_id in enumerate(ids_vectorial):
            rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + 1 / (K_RRF + rango)
        for rango, doc_id in enumerate(ids_bm25):
            rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + 1 / (K_RRF + rango)

        mejores = sorted(rango_reciproco.items(), key=lambda x: x[1], reverse=True)[:k]

        indice_por_id = {doc_id: i for i, doc_id in enumerate(self._ids)}
        resultados = []
        for doc_id, puntaje in mejores:
            i = indice_por_id[doc_id]
            resultados.append(
                {
                    "id": doc_id,
                    "puntaje": round(puntaje, 4),
                    "texto": self._textos[i],
                    **self._metadatas[i],
                }
            )
        return resultados


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    consulta = " ".join(sys.argv[1:]) or "incentivos bienestar social"
    indice = IndiceBusqueda()
    for r in indice.buscar(consulta, k=5):
        print(f"[{r['puntaje']}] {r['titulo_documento']} — {r['url_original']}")
        print("  " + r["texto"][:200].replace("\n", " "))
        print()
