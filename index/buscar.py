"""Búsqueda híbrida sobre el índice: vectorial (Chroma) + léxica (SQLite
FTS5) con fusión por rango recíproco (RRF), como en ReactivosFlow. La
búsqueda léxica importa para citas exactas (números de ley, artículos) que
los embeddings por sí solos suelen perder.

Diseñado para RAM baja: ni el texto completo del corpus ni el índice léxico
viven en memoria de Python — Chroma y FTS5 son ambos disco-residentes, y solo
se trae a RAM lo estrictamente necesario para resolver cada consulta (con
718.388 fragmentos, la versión anterior con rank_bm25 en memoria medía
~10GB de RAM solo para poder arrancar; esta versión no depende del tamaño
del corpus). Esto es lo que hace viable hostear el índice en un servidor
barato en vez de necesitar un plan de ~200 USD/mes solo por RAM."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

# El modelo ya queda cacheado localmente tras la primera descarga; sin esto,
# cada arranque (cada consulta MCP) golpea la red de Hugging Face solo para
# verificar que el caché sigue vigente, lo cual añade latencia innecesaria
# y puede fallar sin conexión.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import chromadb
from sentence_transformers import SentenceTransformer

MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"
DIR_INDICE = Path(__file__).resolve().parent / "chroma_db"
DB_FTS = Path(__file__).resolve().parent / "fts_index.db"
COLECCION = "aliado_libre"
K_RRF = 60
# El embedding multilingüe genérico casi no aporta hallazgos únicos sobre este
# corpus de español jurídico/histórico (medido: de los aciertos de un solo
# método, BM25 explicó el 100% en una muestra de 30 preguntas reales) — pesar
# igual ambos métodos hacía que documentos mediocres en los dos superaran en
# el ranking fusionado a uno que BM25 ya tenía en el puesto #1. Doblar el peso
# de BM25 subió la tasa de acierto en el top-5 de 65% a 72% sobre 40 preguntas
# reales de prueba (ver finetune/ajustar_pesos_rrf.py); pesos más altos (x3, x5)
# no dieron más mejora.
PESO_BM25 = 2.0
PESO_VECTORIAL = 1.0


def _tokenizar(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


def _consulta_fts(tokens: list[str]) -> str:
    # cada token entre comillas dobles: evita que caracteres del texto del
    # usuario (guiones, dos puntos, asteriscos) se interpreten como sintaxis
    # especial de FTS5. OR entre tokens para recall amplio, igual que el
    # BM25 anterior no exigía que todas las palabras aparecieran.
    return " OR ".join(f'"{tok}"' for tok in tokens if tok)


class IndiceBusqueda:
    def __init__(self) -> None:
        self._modelo = SentenceTransformer(MODELO_EMBEDDINGS)
        self._cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
        self._coleccion = self._cliente.get_or_create_collection(COLECCION)
        self._total = self._coleccion.count()

        self._fts: sqlite3.Connection | None = None
        if DB_FTS.exists():
            # solo lectura: el índice FTS5 se construye aparte con index/build_fts.py
            self._fts = sqlite3.connect(f"file:{DB_FTS}?mode=ro", uri=True)

    def buscar(self, consulta: str, k: int = 8) -> list[dict]:
        if self._total == 0:
            return []

        embedding_consulta = self._modelo.encode([consulta]).tolist()
        resultado_vectorial = self._coleccion.query(
            query_embeddings=embedding_consulta, n_results=min(k * 3, self._total)
        )
        ids_vectorial = resultado_vectorial["ids"][0]

        ids_fts: list[str] = []
        if self._fts is not None:
            tokens = _tokenizar(consulta)
            consulta_match = _consulta_fts(tokens)
            if consulta_match:
                cursor = self._fts.execute(
                    "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT ?",
                    (consulta_match, k * 3),
                )
                ids_fts = [fila[0] for fila in cursor.fetchall()]

        rango_reciproco: dict[str, float] = {}
        for rango, doc_id in enumerate(ids_vectorial):
            rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + PESO_VECTORIAL / (K_RRF + rango)
        for rango, doc_id in enumerate(ids_fts):
            rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + PESO_BM25 / (K_RRF + rango)

        mejores = sorted(rango_reciproco.items(), key=lambda x: x[1], reverse=True)[:k]
        if not mejores:
            return []

        # solo se piden a Chroma los ~k documentos ganadores, no el corpus completo
        ids_finales = [doc_id for doc_id, _ in mejores]
        datos = self._coleccion.get(ids=ids_finales, include=["documents", "metadatas"])
        texto_por_id = dict(zip(datos["ids"], datos["documents"], strict=True))
        metadata_por_id = dict(zip(datos["ids"], datos["metadatas"], strict=True))

        resultados = []
        for doc_id, puntaje in mejores:
            if doc_id not in texto_por_id:
                continue  # inconsistencia rara entre Chroma y FTS5 (ej. reindex parcial)
            resultados.append(
                {
                    "id": doc_id,
                    "puntaje": round(puntaje, 4),
                    "texto": texto_por_id[doc_id],
                    **metadata_por_id[doc_id],
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
