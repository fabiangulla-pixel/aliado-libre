"""Construye el índice de búsqueda (Chroma + embeddings locales) a partir de
los JSON de documentos crudos en data/raw/. Sin costo de API: modelo local."""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
    print(f"{len(documentos)} documentos -> {len(fragmentos)} fragmentos")

    modelo = SentenceTransformer(MODELO_EMBEDDINGS)
    textos = [f.texto for f in fragmentos]
    embeddings = modelo.encode(textos, show_progress_bar=True, batch_size=32).tolist()

    cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
    coleccion = cliente.get_or_create_collection(COLECCION)

    metadatas = [
        {
            "documento_id": f.documento_id,
            "fuente": f.fuente,
            "identificador_documento": f.identificador_documento,
            "titulo_documento": f.titulo_documento,
            "url_original": f.url_original,
            "orden": f.orden,
        }
        for f in fragmentos
    ]
    ids = [f.id for f in fragmentos]

    # Chroma limita el tamaño de cada upsert (ver max_batch_size del cliente);
    # se sube en lotes para no reventar con corpus grandes.
    tamanio_lote = 5000
    for inicio in range(0, len(ids), tamanio_lote):
        fin = inicio + tamanio_lote
        coleccion.upsert(
            ids=ids[inicio:fin],
            embeddings=embeddings[inicio:fin],
            documents=textos[inicio:fin],
            metadatas=metadatas[inicio:fin],
        )
        print(f"  lote {inicio}-{min(fin, len(ids))}/{len(ids)} subido", flush=True)

    print(f"Índice actualizado en {DIR_INDICE} ({coleccion.count()} fragmentos totales)")


if __name__ == "__main__":
    dir_por_defecto = Path(__file__).resolve().parent.parent / "data" / "raw"
    dir_raw = Path(sys.argv[1]) if len(sys.argv) > 1 else dir_por_defecto
    construir(dir_raw)
