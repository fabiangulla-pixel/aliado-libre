"""Publica el índice ya construido (index/chroma_db/) como un Dataset público
en Hugging Face Hub, para que cualquiera pueda usar Aliado Libre sin tener
que correr los ingesters ni reconstruir el índice desde cero — solo lo
descarga.

Requiere HF_TOKEN en el entorno (no se pide como argumento para no dejarlo
en el historial de la shell). Generarlo en huggingface.co -> Settings ->
Access Tokens -> New token (permiso "Write").

Uso:
    HF_TOKEN=hf_xxx ./venv/Scripts/python.exe scripts/publicar_indice_hf.py [repo_id]

Por defecto publica en "aliado-libre/indice-legal-colombia"."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

DIR_INDICE = Path(__file__).resolve().parent.parent / "index" / "chroma_db"
REPO_ID_DEFECTO = "aliado-libre/indice-legal-colombia"

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

# Índice legal de Colombia — Aliado Libre

Índice vectorial (ChromaDB + embeddings `paraphrase-multilingual-MiniLM-L12-v2`)
de legislación y jurisprudencia colombiana, construido por
[Aliado Libre](https://github.com/fabiangulla-pixel/aliado-libre) — RAG legal
100% local y gratuito.

## Cómo usarlo

```
git clone https://github.com/fabiangulla-pixel/aliado-libre
cd aliado-libre
huggingface-cli download {repo_id} --repo-type dataset --local-dir index/chroma_db
python mcp_server/server.py
```

## Cobertura y limitaciones

Ver `docs/fuentes.md` en el repo del código para el detalle de qué fuentes
cubre, cuáles están bloqueadas, y las limitaciones conocidas de cada una.
Este índice es una instantánea en el tiempo — no se actualiza en vivo.

## Licencia del contenido

Los documentos indexados son textos oficiales de dominio público (leyes,
decretos, sentencias, conceptos de entidades del Estado colombiano). El
pipeline que construye el índice es software libre (ver el repo de código).
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
    print(f"Listo: https://huggingface.co/datasets/{repo_id}")


if __name__ == "__main__":
    main()
