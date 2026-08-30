"""Crawl del catálogo ABCD/ISIS de Superfinanciera (Conceptos y Jurisprudencia,
18.569 registros). Paginación puramente secuencial, reanuda desde el índice
global donde se quedó la corrida anterior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.superfinanciera import crawl
from ingest.schema import Documento
from scripts._crawl_retry import crawl_con_reintentos

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "superfinanciera.json"


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    def cargar_previos() -> list[Documento]:
        if not SALIDA.exists():
            return []
        datos = json.loads(SALIDA.read_text(encoding="utf-8"))
        return [Documento(**d) for d in datos]

    previos_iniciales = cargar_previos()
    if previos_iniciales:
        print(f"{len(previos_iniciales)} documentos previos cargados, no se vuelven a descargar")

    print(f"Crawl objetivo: {max_documentos} documentos totales, pausa {pausa}s entre requests nuevos")

    def checkpoint(documentos):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    documentos = crawl_con_reintentos(
        crawl,
        checkpoint,
        cargar_previos,
        max_documentos=max_documentos,
        pausa_segundos=pausa,
    )
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
