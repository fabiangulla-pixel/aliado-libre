"""Construye el índice de búsqueda (Chroma + embeddings locales) a partir de
los JSON de documentos crudos en data/raw/. Sin costo de API: modelo local."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # modelo ya cacheado; evita golpear la red en cada corrida

import chromadb
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.chunking import fragmentar
from ingest.schema import Documento

MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"
DIR_INDICE = Path(__file__).resolve().parent / "chroma_db"
COLECCION = "aliado_libre"


def cargar_documentos(dir_raw: Path) -> list[Documento]:
    documentos = []
    for archivo in dir_raw.glob("*.json"):
        if archivo.name.startswith("_"):
            continue
        data = json.loads(archivo.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        for item in items:
            documentos.append(Documento(**item))
    return documentos


def construir(dir_raw: Path) -> None:
    documentos = cargar_documentos(dir_raw)
    if not documentos:
        print(f"No hay documentos en {dir_raw}")
        return

    fragmentos = []
    for doc in documentos:
        fragmentos.extend(fragmentar(doc))
    print(f"{len(documentos)} documentos -> {len(fragmentos)} fragmentos", flush=True)

    modelo = SentenceTransformer(MODELO_EMBEDDINGS)
    cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
    coleccion = cliente.get_or_create_collection(COLECCION)

    # Embeddings + upsert por lote (no un solo encode() de todo el corpus
    # seguido de upsert al final): con corpus grandes (cientos de miles de
    # fragmentos) el cómputo puede tomar horas, y un proceso así de largo en
    # background puede morir sin traza (presión de memoria del sistema,
    # sobre todo si compite con otro proceso pesado en la misma máquina —
    # pasó de verdad en esta sesión). Con upsert incremental, matar el
    # proceso a mitad de camino pierde solo el lote en curso, no todo.
    tamanio_lote = 2000
    total = len(fragmentos)
    for inicio in range(0, total, tamanio_lote):
        lote = fragmentos[inicio : inicio + tamanio_lote]
        textos = [f.texto for f in lote]
        embeddings = modelo.encode(textos, batch_size=32).tolist()
        ids = [f.id for f in lote]
        metadatas = [
            {
                "documento_id": f.documento_id,
                "fuente": f.fuente,
                "identificador_documento": f.identificador_documento,
                "titulo_documento": f.titulo_documento,
                "url_original": f.url_original,
                "orden": f.orden,
            }
            for f in lote
        ]
        coleccion.upsert(ids=ids, embeddings=embeddings, documents=textos, metadatas=metadatas)
        print(f"  lote {inicio}-{min(inicio + tamanio_lote, total)}/{total} subido", flush=True)

    print(f"Índice actualizado en {DIR_INDICE} ({coleccion.count()} fragmentos totales)")


if __name__ == "__main__":
    dir_por_defecto = Path(__file__).resolve().parent.parent / "data" / "raw"
    dir_raw = Path(sys.argv[1]) if len(sys.argv) > 1 else dir_por_defecto
    construir(dir_raw)
