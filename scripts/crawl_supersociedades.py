"""Crawl de Supersociedades (Tesauro) sobre Elasticsearch con search_after.
Reanuda: lo que ya está en data/raw se conserva y no se vuelve a pedir."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.supersociedades import crawl
from ingest.schema import Documento

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "supersociedades.json"


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    previos = (
        [Documento(**d) for d in json.loads(SALIDA.read_text(encoding="utf-8"))] if SALIDA.exists() else []
    )
    print(f"{len(previos)} previos; objetivo {max_documentos} documentos, pausa {pausa}s entre páginas")

    def checkpoint(documentos):
        tmp = SALIDA.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(SALIDA)
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    documentos = crawl(
        max_documentos=max_documentos, pausa_segundos=pausa, al_guardar=checkpoint, documentos_previos=previos
    )
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos ({len(documentos) - len(previos)} nuevos) en {SALIDA}")


if __name__ == "__main__":
    main()
