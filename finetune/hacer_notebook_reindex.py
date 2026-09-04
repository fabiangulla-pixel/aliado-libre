"""Genera el .ipynb de Colab a partir de finetune/colab_reindexar_embeddings.py.

El código del notebook vive en un .py normal para que pase por ruff y se pueda
revisar en un diff legible; el .ipynb es un artefacto derivado.

Uso:
    ./venv/Scripts/python.exe finetune/hacer_notebook_reindex.py
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def main() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_fuente", RAIZ / "colab_reindexar_embeddings.py")
    fuente = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fuente)

    celdas = []
    for tipo, texto in fuente.CELDAS:
        lineas = texto.strip("\n").split("\n")
        fuente_celda = [f"{linea}\n" for linea in lineas[:-1]] + [lineas[-1]]
        if tipo == "code":
            celdas.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": fuente_celda,
                }
            )
        else:
            celdas.append({"cell_type": "markdown", "metadata": {}, "source": fuente_celda})

    notebook = {
        "cells": celdas,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4"},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }
    salida = RAIZ / "colab_reindexar_embeddings.ipynb"
    salida.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Escrito {salida} ({len(celdas)} celdas)")


if __name__ == "__main__":
    main()
