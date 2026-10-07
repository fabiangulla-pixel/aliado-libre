"""Crawl de los conceptos de Superservicios, año por año, con checkpoint.

Uso:
    .venv/Scripts/python.exe scripts/crawl_superservicios.py            # 1994-hoy
    .venv/Scripts/python.exe scripts/crawl_superservicios.py 2024 2025  # solo esos años
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.superservicios import crawl  # noqa: E402
from ingest.schema import Documento  # noqa: E402

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "superservicios.json"


def main() -> None:
    anios = [int(a) for a in sys.argv[1:]] or list(range(date.today().year, 1993, -1))
    previos: list[Documento] = []
    if SALIDA.exists():
        previos = [Documento(**d) for d in json.loads(SALIDA.read_text(encoding="utf-8"))]
        print(f"{len(previos)} documentos previos: no se vuelven a descargar")

    def guardar(documentos: list[Documento]) -> None:
        tmp = SALIDA.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tmp.replace(SALIDA)
        print(f"  [checkpoint] {len(documentos)} documentos", flush=True)

    documentos = crawl(anios, documentos_previos=previos, al_guardar=guardar)
    guardar(documentos)
    print(f"Terminado: {len(documentos)} conceptos en {SALIDA}")


if __name__ == "__main__":
    main()
