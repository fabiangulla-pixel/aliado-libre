"""Construye el índice léxico FTS5 (SQLite, en disco) a partir de lo que ya
hay en Chroma — reemplaza a rank_bm25, que exigía tener los 718k fragmentos
completos cargados en RAM en todo momento (~10GB medidos) solo para poder
buscar por texto exacto. FTS5 vive en disco y solo trae a memoria lo que
hace falta para responder cada consulta puntual.

Se corre una sola vez después de construir/actualizar el índice de Chroma
(build_index.py) — index/buscar.py después solo LEE este archivo, nunca
reconstruye el índice léxico en memoria.

Uso:
    ./venv/Scripts/python.exe index/build_fts.py
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import chromadb

DIR_INDICE = Path(__file__).resolve().parent / "chroma_db"
COLECCION = "aliado_libre"
DB_FTS = Path(__file__).resolve().parent / "fts_index.db"


def construir() -> None:
    cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
    coleccion = cliente.get_or_create_collection(COLECCION)
    total = coleccion.count()
    if total == 0:
        print("La colección de Chroma está vacía — nada que indexar.")
        return

    if DB_FTS.exists():
        DB_FTS.unlink()  # reconstrucción completa, no incremental (simple y confiable)

    conexion = sqlite3.connect(str(DB_FTS))
    conexion.execute(
        "CREATE VIRTUAL TABLE fragmentos_fts "
        "USING fts5(id UNINDEXED, texto, tokenize='unicode61 remove_diacritics 2')"
    )

    tamanio_lote = 5000
    offset = 0
    insertados = 0
    while True:
        lote = coleccion.get(include=["documents"], limit=tamanio_lote, offset=offset)
        if not lote["ids"]:
            break
        conexion.executemany(
            "INSERT INTO fragmentos_fts (id, texto) VALUES (?, ?)",
            zip(lote["ids"], lote["documents"], strict=True),
        )
        insertados += len(lote["ids"])
        offset += len(lote["ids"])
        print(f"  {insertados}/{total} fragmentos indexados en FTS5", flush=True)

    conexion.commit()
    conexion.execute("INSERT INTO fragmentos_fts(fragmentos_fts) VALUES ('optimize')")  # compacta el índice
    conexion.commit()
    conexion.close()

    tamano_mb = DB_FTS.stat().st_size / (1024 * 1024)
    print(f"\nÍndice FTS5 construido en {DB_FTS} ({tamano_mb:.0f} MB en disco, {insertados} fragmentos)")


if __name__ == "__main__":
    construir()
