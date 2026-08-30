"""Lectura del respaldo local de legalize-co (sin red) — 71.900 archivos
Markdown con YAML front matter. `max_documentos` limita el tamaño de cada
checkpoint, no el total real (correr varias veces hasta agotar el repo)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.legalize_co_github import crawl
from ingest.schema import Documento

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "legalize_co_github.json"


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 80000

    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    documentos_previos: list[Documento] = []
    if SALIDA.exists():
        datos = json.loads(SALIDA.read_text(encoding="utf-8"))
        documentos_previos = [Documento(**d) for d in datos]
        print(f"{len(documentos_previos)} documentos previos cargados, no se vuelven a releer")

    print(f"Objetivo: {max_documentos} documentos totales (lectura local, sin red)")

    def checkpoint(documentos):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    documentos = crawl(
        max_documentos=max_documentos, al_guardar=checkpoint, documentos_previos=documentos_previos
    )
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
