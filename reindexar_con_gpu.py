#!/usr/bin/env python3
"""Reindexación completa con chunking mejorado, usando GPU."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import chromadb
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest.chunking import fragmentar
from ingest.schema import Documento

DIR_INDICE = Path(__file__).resolve().parent / "index" / "chroma_db"
DB_FTS = Path(__file__).resolve().parent / "index" / "fts_index.db"
from index.buscar import COLECCION, MODELO_EMBEDDINGS, PREFIJO_PASAJE  # noqa: E402


def cargar_documentos(dir_raw: Path) -> list[Documento]:
    documentos = []
    for archivo in sorted(dir_raw.glob("*.json")):
        if archivo.name.startswith("_"):
            continue
        data = json.loads(archivo.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        for item in items:
            documentos.append(Documento(**item))
    return documentos


def reindexar(dir_raw: Path) -> None:
    documentos = cargar_documentos(dir_raw)
    if not documentos:
        print(f"No hay documentos en {dir_raw}")
        return

    print(f"Cargados {len(documentos)} documentos")

    fragmentos = []
    for i, doc in enumerate(documentos, 1):
        frags = fragmentar(doc)
        fragmentos.extend(frags)
        if i % 50 == 0:
            print(f"  {i}/{len(documentos)} documentos procesados ({len(fragmentos)} fragmentos)")

    print(f"Total: {len(fragmentos)} fragmentos después del chunking mejorado")

    # El índice anterior NO se borra: se reanuda sobre él. La versión destructiva
    # de este script borraba Chroma y el FTS antes de empezar, así que una corrida
    # interrumpida dejaba el proyecto sin índice utilizable y sin aviso — fue lo
    # que pasó el 9-sep-2026, que terminó con 158.000 fragmentos de los 226.000
    # anunciados y el índice léxico borrado y nunca reconstruido.
    # Cargar modelo con GPU (device_map automático)
    print("Cargando modelo de embeddings (GPU si está disponible)...")
    modelo = SentenceTransformer(MODELO_EMBEDDINGS)
    print(f"  Modelo en device: {modelo.device}")

    # Crear cliente Chroma
    cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
    coleccion = cliente.get_or_create_collection(COLECCION)

    # Reanudar: lo que ya está indexado no se vuelve a codificar. Sin esto, una
    # corrida de horas que se cae obliga a empezar de cero.
    ya_estan: set[str] = set()
    if coleccion.count():
        desplazamiento = 0
        while True:
            pagina = coleccion.get(include=[], limit=50000, offset=desplazamiento)
            if not pagina["ids"]:
                break
            ya_estan.update(pagina["ids"])
            desplazamiento += len(pagina["ids"])
        print(f"Ya indexados: {len(ya_estan)} fragmentos; se reanuda sobre ellos")
    pendientes = [f for f in fragmentos if f.id not in ya_estan]
    print(f"Pendientes de indexar: {len(pendientes)}")

    # Upsert incremental con GPU
    tamanio_lote = 1000
    total = len(pendientes)
    for inicio in range(0, total, tamanio_lote):
        lote = pendientes[inicio : inicio + tamanio_lote]
        textos = [f.texto for f in lote]

        # batch_size > 1 usa más memoria pero aprovecha mejor la GPU
        print(f"  Codificando fragmentos {inicio}-{min(inicio + tamanio_lote, total)}/{total}...")
        embeddings = modelo.encode(
            [PREFIJO_PASAJE + t for t in textos], batch_size=64, show_progress_bar=True
        ).tolist()

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

        print("  Subiendo lote...")
        coleccion.upsert(ids=ids, embeddings=embeddings, documents=textos, metadatas=metadatas)

    indexados = coleccion.count()
    print(f"\nChroma: {indexados} fragmentos ({len(fragmentos)} esperados)")
    if indexados < len(fragmentos):
        raise SystemExit(
            f"Reindexacion INCOMPLETA: faltan {len(fragmentos) - indexados} fragmentos. "
            "Volver a correr este script; reanuda donde quedo."
        )

    # El indice lexico se reconstruye aqui, encadenado: dejarlo como un segundo
    # paso manual es justo lo que fallo el 9-sep-2026.
    print("Reconstruyendo el indice lexico FTS5...")
    if DB_FTS.exists():
        DB_FTS.unlink()
    from index.build_fts import construir as construir_fts

    construir_fts()
    print(f"\nReindexacion completada: {indexados} fragmentos + indice lexico")
    print(f"Indices en: {DIR_INDICE}")


if __name__ == "__main__":
    dir_por_defecto = Path(__file__).resolve().parent / "data" / "raw"
    dir_raw = Path(sys.argv[1]) if len(sys.argv) > 1 else dir_por_defecto
    reindexar(dir_raw)
