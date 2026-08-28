"""Crawl de SIC: paginación simple sobre Elasticsearch + descarga de PDF vía
URL firmada por cada resultado (más lento que las otras fuentes: 2 requests
extra y parseo de PDF por documento, no solo 1 request de metadata)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.sic import crawl

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "sic.json"


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5

    print(f"Crawl objetivo: {max_documentos} documentos, pausa {pausa}s entre PDFs")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(documentos):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    documentos = crawl(max_documentos=max_documentos, pausa_segundos=pausa, al_guardar=checkpoint)
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
