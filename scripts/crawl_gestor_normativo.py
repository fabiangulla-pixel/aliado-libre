"""Lanza un crawl real de Gestor Normativo a partir de varias normas semilla
importantes, guardando avances incrementalmente (checkpoint) para poder
reanudar si se interrumpe."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.gestor_normativo import crawl

# Semillas: decretos únicos reglamentarios de varios sectores (alta densidad
# de relaciones "Vigencias" -> el BFS se expande rápido a normas relacionadas).
SEMILLAS = [
    "62866",  # Decreto 1083 de 2015 - Función Pública
    "62703",  # Decreto 1072 de 2015 - Trabajo
    "62477",  # Decreto 1071 de 2015 - Agropecuario
    "62258",  # Decreto 1069 de 2015 - Defensa
    "62255",  # (categoría decretos únicos, referencia adicional)
]

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "gestor_normativo.json"
CHECKPOINT_CADA = 25


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5

    print(f"Crawl objetivo: {max_documentos} documentos, pausa {pausa}s entre requests")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(documentos):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    documentos = crawl(SEMILLAS, max_documentos=max_documentos, pausa_segundos=pausa, al_guardar=checkpoint)
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
