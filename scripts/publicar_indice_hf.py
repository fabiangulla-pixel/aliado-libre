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
| `chroma.sqlite3` + carpetas UUID | Indice vectorial ChromaDB | ~19 GB |
| `fts_index.db` | Indice lexico SQLite FTS5 (BM25 en disco) | ~1,6 GB |

## Que embeddings tiene, y por que hay dos colecciones

La coleccion que usa el codigo hoy es **`aliado_libre_multilingual_e5_large`**
(`intfloat/multilingual-e5-large`, 1024 dimensiones, 512 tokens de ventana).

Se conserva ademas la coleccion anterior `aliado_libre`
(`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensiones), que ya no se usa.
El motivo del cambio, medido sobre este mismo corpus: aquel modelo tiene una
ventana de **128 tokens** (~450 caracteres) y el **76% de los fragmentos pasa
de 500 caracteres**, asi que en tres de cada cuatro el vector solo representaba
el encabezado - que en una norma no es la parte que responde. Encima era un
modelo de *parafrasis* donde hace falta uno de *recuperacion*: una pregunta
hecha con palabras corrientes y el articulo que la responde no se parecen en la
superficie.

Los vectores en crudo estan tambien como
`embeddings_multilingual-e5-large.f16.npy` (718.388 x 1024, float16) con sus
identificadores en `ids_multilingual-e5-large.json`, por si prefieres montar tu
propio indice en vez de usar el de Chroma.

**Los prefijos de e5 no son opcionales**: al consultar hay que anteponer
`query: ` a la pregunta, porque asi se construyo el indice. Sin eso la busqueda
empeora sin dar ningun error.

## La busqueda es hibrida

Se **fusionan ambos indices con RRF**: el vectorial encuentra por significado, el
lexico por termino exacto (numeros de norma, articulos, nombres propios). El
FTS5 vive en disco a proposito - sustituyo a `rank_bm25`, que cargaba el corpus
entero en memoria.

## Como usarlo

```bash
git clone https://github.com/fabiangulla-pixel/aliado-libre
cd aliado-libre
huggingface-cli download {repo_id} --repo-type dataset --local-dir /tmp/indice
mv /tmp/indice/fts_index.db index/fts_index.db
mv /tmp/indice/* index/chroma_db/
python mcp_server/server.py
```

Necesitas ~21 GB de disco. La memoria RAM necesaria **se esta volviendo a medir**
tras el cambio de modelo: la cifra anterior (2,3 GB) correspondia al embedding
viejo, que pesaba unas cuatro veces menos. Cuenta con mas.

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

Sobre la calidad de la recuperacion: se esta midiendo con un banco propio de
consultas y **todavia no esta en el nivel que justificaria publicar cifras**.
Cuando lo este, se publicaran aqui.

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
