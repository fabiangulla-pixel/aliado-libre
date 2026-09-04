"""Reconstruye la colección de Chroma a partir de vectores YA calculados.

La contraparte local de `finetune/colab_reindexar_embeddings.ipynb`: Colab hace
lo caro (recalcular 718.388 embeddings en GPU) y publica la matriz en Hugging
Face; esto solo la descarga y la inserta. No carga ningún modelo, así que no
necesita torch ni GPU y tarda minutos, no horas.

Escribe en una colección NUEVA, no encima de la que está en uso: hasta que la
medición diga que el índice nuevo es mejor, el viejo tiene que seguir
funcionando. Cambiar de uno a otro es cambiar `COLECCION` en index/buscar.py.

Uso:
    HF_TOKEN=... ./venv/Scripts/python.exe index/build_index_desde_vectores.py \
        --modelo intfloat/multilingual-e5-large
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DIR_INDICE = RAIZ / "chroma_db"
CHROMA_SQLITE = DIR_INDICE / "chroma.sqlite3"
REPO = "Gullax/indice-legal-colombia"
LOTE = 2000  # mismo tamaño que build_index.py: pasar de aquí revienta Chroma


def _metadata_por_id() -> dict[str, dict]:
    """Lee del Chroma actual el texto y la metadata de cada fragmento.

    Los documentos no cambian al reindexar — cambia solo su representación
    vectorial — así que se reutilizan en vez de volver a bajar el corpus.
    """
    con = sqlite3.connect(f"file:{CHROMA_SQLITE}?mode=ro", uri=True)
    campos: dict[str, dict] = {}
    for fila_id, clave, valor in con.execute("SELECT id, key, string_value FROM embedding_metadata"):
        campos.setdefault(fila_id, {})[clave] = valor
    ids_por_fila = dict(con.execute("SELECT id, embedding_id FROM embeddings"))

    salida: dict[str, dict] = {}
    for fila_id, datos in campos.items():
        frag_id = ids_por_fila.get(fila_id)
        if not frag_id:
            continue
        texto = (datos.get("chroma:document") or "").strip()
        if not texto:
            continue
        salida[frag_id] = {
            "texto": texto,
            "metadata": {k: v for k, v in datos.items() if k != "chroma:document" and v is not None},
        }
    return salida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--modelo", default="intfloat/multilingual-e5-large")
    p.add_argument("--coleccion", default="", help="nombre de la colección nueva")
    args = p.parse_args()

    sufijo = args.modelo.split("/")[-1]
    coleccion_nueva = args.coleccion or f"aliado_libre_{sufijo.replace('-', '_')}"

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("Falta HF_TOKEN en el entorno.")

    import numpy as np
    from huggingface_hub import hf_hub_download

    print(f"Descargando vectores de {REPO} ({sufijo})...")
    ruta_vec = hf_hub_download(
        repo_id=REPO, filename=f"embeddings_{sufijo}.f16.npy", repo_type="dataset", token=token
    )
    ruta_ids = hf_hub_download(repo_id=REPO, filename=f"ids_{sufijo}.json", repo_type="dataset", token=token)
    vectores = np.load(ruta_vec)
    ids = json.loads(Path(ruta_ids).read_text(encoding="utf-8"))
    print(f"{vectores.shape[0]} vectores de {vectores.shape[1]} dimensiones")

    if len(ids) != vectores.shape[0]:
        raise SystemExit(
            f"Descuadre: {len(ids)} ids frente a {vectores.shape[0]} vectores. "
            "La matriz y el orden de ids tienen que venir de la misma corrida."
        )

    print("Leyendo textos y metadata del índice actual...")
    contenido = _metadata_por_id()
    faltantes = [i for i in ids if i not in contenido]
    if faltantes:
        print(f"AVISO: {len(faltantes)} ids sin texto en el índice local; se omiten.")

    import chromadb

    cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
    coleccion = cliente.get_or_create_collection(coleccion_nueva)
    print(f"Colección destino: {coleccion_nueva} (la actual no se toca)")

    utiles = [(i, v) for i, v in zip(ids, vectores, strict=True) if i in contenido]
    total = len(utiles)
    for inicio in range(0, total, LOTE):
        trozo = utiles[inicio : inicio + LOTE]
        coleccion.upsert(
            ids=[i for i, _ in trozo],
            embeddings=[v.astype("float32").tolist() for _, v in trozo],
            documents=[contenido[i]["texto"] for i, _ in trozo],
            metadatas=[contenido[i]["metadata"] for i, _ in trozo],
        )
        hechos = min(inicio + LOTE, total)
        print(f"  {hechos}/{total}", flush=True)

    print(f"\nListo: {coleccion.count()} fragmentos en '{coleccion_nueva}'.")
    print("Para probarlo sin romper lo actual:")
    print(f"  ALIADO_COLECCION={coleccion_nueva} ALIADO_MODELO_EMBEDDINGS={args.modelo} \\")
    print("      ./venv/Scripts/python.exe finetune/medir_recuperacion.py")


if __name__ == "__main__":
    sys.exit(main())
