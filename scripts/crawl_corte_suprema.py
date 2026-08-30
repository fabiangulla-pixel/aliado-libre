"""Crawl de la Corte Suprema de Justicia vía el backend GraphQL propio
(consultaprovidenciasbk.cortesuprema.gov.co/api). Corpus enorme (>1M
resultados brutos entre las 4 Salas) y backend inestable (502 intermitente):
correr en lotes moderados, con pausa generosa, y reanudar seguido."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import urllib3

warnings.filterwarnings("ignore")
urllib3.disable_warnings()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.corte_suprema import crawl
from ingest.schema import Documento
from scripts._crawl_retry import crawl_con_reintentos

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "corte_suprema.json"


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5

    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    def cargar_previos() -> list[Documento]:
        if not SALIDA.exists():
            return []
        datos = json.loads(SALIDA.read_text(encoding="utf-8"))
        return [Documento(**d) for d in datos]

    previos_iniciales = cargar_previos()
    if previos_iniciales:
        print(f"{len(previos_iniciales)} documentos previos cargados, no se vuelven a descargar")

    print(f"Crawl objetivo: {max_documentos} documentos totales, pausa {pausa}s entre providencias")

    def checkpoint(documentos):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    # El backend GraphQL de la Corte Suprema falla con 502 en ráfagas de
    # varios minutos (visto en la sesión que escribió este ingester) — el
    # ingester ya reintenta cada llamada individual 3 veces, pero si la
    # ráfaga dura más que eso, se reintenta la corrida completa reanudando
    # desde el último checkpoint en vez de perder todo el lote.
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
