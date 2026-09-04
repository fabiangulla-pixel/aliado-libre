"""Publica el índice ya construido (index/chroma_db/) como un Dataset público
en Hugging Face Hub, para que cualquiera pueda usar Aliado Libre sin tener
que correr los ingesters ni reconstruir el índice desde cero — solo lo
descarga.

Requiere HF_TOKEN en el entorno (no se pide como argumento para no dejarlo
en el historial de la shell). Generarlo en huggingface.co -> Settings ->
Access Tokens -> New token (permiso "Write").

Uso:
    HF_TOKEN=hf_xxx ./venv/Scripts/python.exe scripts/publicar_indice_hf.py [repo_id]

Por defecto publica en "Gullax/indice-legal-colombia"."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

DIR_INDICE = Path(__file__).resolve().parent.parent / "index" / "chroma_db"
# El FTS5 vive fuera de chroma_db pero la busqueda lo necesita igual: publicar
# solo el vectorial deja el dataset inservible para quien lo descargue.
RUTA_FTS = Path(__file__).resolve().parent.parent / "index" / "fts_index.db"
REPO_ID_DEFECTO = "Gullax/indice-legal-colombia"

TARJETA_DATASET = """---
license: other
language:
- es
tags:
- legal
- colombia
- rag
- chromadb
---

# Indice legal de Colombia - Aliado Libre

Indice de legislacion y jurisprudencia colombiana: **718.388 fragmentos** de
**119.708 documentos** oficiales, construido por
[Aliado Libre](https://github.com/fabiangulla-pixel/aliado-libre) - RAG legal
gratuito y de codigo abierto.

Son **dos piezas**, y la busqueda necesita las dos:

| Archivo | Que es | Tamano |
|---|---|---|
| `chroma.sqlite3` + carpeta UUID | Indice vectorial ChromaDB | ~9,1 GB |
| `fts_index.db` | Indice lexico SQLite FTS5 (BM25 en disco) | ~1,6 GB |

Los embeddings del indice vectorial son `paraphrase-multilingual-MiniLM-L12-v2`.

La busqueda **fusiona ambos con RRF**: el vectorial encuentra por significado,
el lexico por termino exacto (numeros de norma, articulos, nombres propios).
El FTS5 vive en disco a proposito - sustituyo a `rank_bm25`, que cargaba el
corpus entero en memoria, y bajo la RAM del indice de **10 GB a 2,3 GB**.

## Como usarlo

```bash
git clone https://github.com/fabiangulla-pixel/aliado-libre
cd aliado-libre
huggingface-cli download {repo_id} --repo-type dataset --local-dir /tmp/indice
mv /tmp/indice/fts_index.db index/fts_index.db
mv /tmp/indice/* index/chroma_db/
python mcp_server/server.py
```

Necesitas ~11 GB de disco y ~2,3 GB de RAM libre.

## Fuentes cubiertas

Corte Constitucional, Gestor Normativo (Funcion Publica), Supersociedades,
SIC, DIAN, Superfinanciera y el respaldo `legalize-co` de decretos.

**Dos huecos conocidos, y son de origen, no del pipeline:** el Consejo de
Estado esta bloqueado por el WAF de la Rama Judicial, y la Corte Suprema
tiene su backend GraphQL devolviendo 502 de forma persistente. Detalle en
`docs/fuentes.md`.

## Limitaciones

Es una **instantanea en el tiempo**: no se actualiza en vivo, asi que una
norma derogada o una sentencia posterior a la fecha de construccion no se
reflejan. No sustituye asesoria juridica profesional.

## Licencia del contenido

Los documentos indexados son textos oficiales de dominio publico (leyes,
decretos, sentencias, conceptos de entidades del Estado colombiano). El
pipeline que construye el indice es software libre (ver el repo de codigo).
"""


def main() -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("Falta HF_TOKEN en el entorno. Generar en huggingface.co -> Settings -> Access Tokens.")
        sys.exit(1)

    if not DIR_INDICE.exists():
        print(f"No existe {DIR_INDICE} — construir el índice primero con index/build_index.py")
        sys.exit(1)

    repo_id = sys.argv[1] if len(sys.argv) > 1 else REPO_ID_DEFECTO

    api = HfApi(token=token)
    print(f"Creando/verificando dataset {repo_id}...")
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True, private=False)

    tarjeta = TARJETA_DATASET.replace("{repo_id}", repo_id)
    (DIR_INDICE / "README.md").write_text(tarjeta, encoding="utf-8")

    print(f"Subiendo {DIR_INDICE} a {repo_id} (puede tardar según el tamaño del índice)...")
    api.upload_folder(
        folder_path=str(DIR_INDICE),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Actualizar índice de Aliado Libre",
    )
    if RUTA_FTS.exists():
        print(f"Subiendo {RUTA_FTS.name} ({RUTA_FTS.stat().st_size / 1024**3:.1f} GB)...")
        api.upload_file(
            path_or_fileobj=str(RUTA_FTS),
            path_in_repo=RUTA_FTS.name,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message="Actualizar indice FTS5",
        )
    else:
        print(f"AVISO: no existe {RUTA_FTS} — el dataset quedara sin el indice lexico.")

    print(f"Listo: https://huggingface.co/datasets/{repo_id}")


if __name__ == "__main__":
    main()
