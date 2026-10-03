#!/usr/bin/env python3
"""Repara en el índice los fragmentos con doble codificación UTF-8, sin reindexar todo.

Medido el 3-oct-2026: ~28.700 fragmentos (64 documentos del Gestor, entre ellos
el Código de Comercio, y unos cientos de otras fuentes). Para cada fragmento
dañado se repara el texto (`ingest/codificacion.py`), se vuelve a calcular su
embedding con la misma configuración que el indexador (`reindexar_con_gpu.py`:
TF32, prefijo de pasaje, sin normalizar) y se actualizan Chroma y el FTS5.

Antes de tocar nada guarda el texto y el título originales en
`_run/reparacion_codificacion_respaldo.jsonl`: `--revertir` los restaura
(recalculando sus embeddings).

No correr con el servidor encendido: Chroma y el FTS se escriben en sitio.

Uso:
    .venv/Scripts/python.exe scripts/reparar_codificacion_indice.py --contar
    .venv/Scripts/python.exe scripts/reparar_codificacion_indice.py --reparar
    .venv/Scripts/python.exe scripts/reparar_codificacion_indice.py --revertir
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from index.buscar import COLECCION, DB_FTS, DIR_INDICE, MODELO_EMBEDDINGS, PREFIJO_PASAJE  # noqa: E402
from ingest.codificacion import reparar, tiene_mojibake  # noqa: E402

RESPALDO = RAIZ / "_run" / "reparacion_codificacion_respaldo.jsonl"
LOTE = 256


def ids_sospechosos() -> list[str]:
    """Ids cuyo texto o título tiene marcas de mojibake (filtro grueso en SQL, fino en Python)."""
    con = sqlite3.connect(f"file:{Path(DIR_INDICE) / 'chroma.sqlite3'}?mode=ro", uri=True)
    filas = con.execute(
        """select e.embedding_id, m.string_value from embedding_metadata m join embeddings e on e.id = m.id
           where m.key in ('chroma:document', 'titulo_documento')
             and (m.string_value like '%Ã%' or m.string_value like '%Â%')"""
    ).fetchall()
    con.close()
    return sorted({i for i, texto in filas if tiene_mojibake(texto)})


def _modelo():
    import torch
    from sentence_transformers import SentenceTransformer

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.set_float32_matmul_precision("high")
    return SentenceTransformer(MODELO_EMBEDDINGS)


def _escribir(col, fts, ids, textos, metas, modelo) -> None:
    emb = modelo.encode([PREFIJO_PASAJE + t for t in textos], batch_size=64).tolist()
    col.update(ids=ids, documents=textos, embeddings=emb, metadatas=metas)
    fts.executemany("UPDATE fragmentos_fts SET texto = ? WHERE id = ?", list(zip(textos, ids, strict=True)))
    fts.commit()


def reparar_indice() -> int:
    import chromadb

    ids = ids_sospechosos()
    print(f"{len(ids)} fragmentos con mojibake", flush=True)
    if RESPALDO.exists():
        print(f"Ya existe {RESPALDO}: una reparación previa. Revierte o muévelo antes de repetir.")
        return 1
    col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    fts = sqlite3.connect(str(DB_FTS))
    modelo = _modelo()
    RESPALDO.parent.mkdir(exist_ok=True)
    cambiados = 0
    t0 = time.time()
    with RESPALDO.open("w", encoding="utf-8") as resp:
        for j in range(0, len(ids), LOTE):
            lote = ids[j : j + LOTE]
            datos = col.get(ids=lote, include=["documents", "metadatas"])
            nuevos_ids, nuevos_textos, nuevas_metas = [], [], []
            for i, texto, meta in zip(datos["ids"], datos["documents"], datos["metadatas"], strict=True):
                meta = dict(meta or {})
                texto_rep = reparar(texto or "")
                titulo = meta.get("titulo_documento") or ""
                titulo_rep = reparar(titulo)
                if texto_rep == texto and titulo_rep == titulo:
                    continue
                resp.write(json.dumps({"id": i, "texto": texto, "titulo": titulo}, ensure_ascii=False) + "\n")
                meta["titulo_documento"] = titulo_rep
                nuevos_ids.append(i)
                nuevos_textos.append(texto_rep)
                nuevas_metas.append(meta)
            if nuevos_ids:
                _escribir(col, fts, nuevos_ids, nuevos_textos, nuevas_metas, modelo)
                cambiados += len(nuevos_ids)
            resp.flush()
            print(
                f"  {min(j + LOTE, len(ids))}/{len(ids)}  reparados {cambiados}  {time.time() - t0:.0f}s",
                flush=True,
            )
    fts.close()
    print(f"Listo: {cambiados} fragmentos reparados. Respaldo en {RESPALDO}")
    print("Reconstruye el catálogo de citas: index/resolver_citas.py --construir")
    return 0


def revertir() -> int:
    import chromadb

    if not RESPALDO.exists():
        print("No hay respaldo que revertir.")
        return 1
    filas = [json.loads(x) for x in RESPALDO.read_text(encoding="utf-8").splitlines() if x.strip()]
    col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    fts = sqlite3.connect(str(DB_FTS))
    modelo = _modelo()
    for j in range(0, len(filas), LOTE):
        lote = filas[j : j + LOTE]
        metas = col.get(ids=[f["id"] for f in lote], include=["metadatas"])["metadatas"]
        metas = [{**(m or {}), "titulo_documento": f["titulo"]} for m, f in zip(metas, lote, strict=True)]
        _escribir(col, fts, [f["id"] for f in lote], [f["texto"] for f in lote], metas, modelo)
    fts.close()
    RESPALDO.rename(RESPALDO.with_suffix(".revertido.jsonl"))
    print(f"Revertidos {len(filas)} fragmentos.")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--contar", action="store_true")
    g.add_argument("--reparar", action="store_true")
    g.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    if a.contar:
        ids = ids_sospechosos()
        docs = {i.split("::")[0] for i in ids}
        print(f"{len(ids)} fragmentos en {len(docs)} documentos")
        return 0
    return reparar_indice() if a.reparar else revertir()


if __name__ == "__main__":
    raise SystemExit(main())
