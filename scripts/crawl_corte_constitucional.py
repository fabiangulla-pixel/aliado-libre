"""Crawl completo de la Corte Constitucional: un request por año (1992-hoy),
no por documento. Guarda checkpoint tras cada año."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.corte_constitucional import crawl

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "corte_constitucional.json"


def main() -> None:
    pausa = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(documentos):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    documentos = crawl(anio_inicio=1992, pausa_segundos=pausa, al_guardar=checkpoint)
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
