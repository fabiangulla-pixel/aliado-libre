"""Crawl de la doctrina de la Compilación Jurídica de Supersalud: conceptos de la
Superintendencia Nacional de Salud y del Ministerio de Salud, año por año.

Mismo sistema de normograma que Superservicios (ingest/fuentes/superservicios.py).
Es una selección (~40-70 conceptos por año desde ~2014), no la doctrina completa,
pero es la que cubre EPS, IPS, autorizaciones y afiliación.

Uso:
    .venv/Scripts/python.exe scripts/crawl_supersalud.py
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

BASE = "https://normograma.supersalud.gov.co/compilacion/"
PAGINAS = ("cjd_occ_superintendencia_nacional_salud", "cjd_occ_ministerio_salud_proteccion_social")
SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "supersalud.json"


def main() -> None:
    previos: list[Documento] = []
    if SALIDA.exists():
        previos = [Documento(**d) for d in json.loads(SALIDA.read_text(encoding="utf-8"))]

    def guardar(documentos: list[Documento]) -> None:
        tmp = SALIDA.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tmp.replace(SALIDA)

    anios = list(range(date.today().year, 1993, -1))
    documentos = crawl(
        anios, documentos_previos=previos, al_guardar=guardar, base=BASE, paginas=PAGINAS, fuente="supersalud"
    )
    guardar(documentos)
    print(f"Terminado: {len(documentos)} conceptos en {SALIDA}")


if __name__ == "__main__":
    main()
