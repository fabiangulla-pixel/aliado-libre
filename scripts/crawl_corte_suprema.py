"""Crawl de la Corte Suprema de Justicia vía el backend GraphQL propio
(consultaprovidenciasbk.cortesuprema.gov.co/api). Corpus enorme (>1M
resultados brutos entre las 4 Salas) y backend inestable (502 intermitente):
correr en lotes moderados, con pausa generosa, y reanudar seguido."""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import urllib3

warnings.filterwarnings("ignore")
urllib3.disable_warnings()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.corte_suprema import crawl
from ingest.schema import Documento

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "corte_suprema.json"


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5

    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    documentos_previos: list[Documento] = []
    if SALIDA.exists():
        datos = json.loads(SALIDA.read_text(encoding="utf-8"))
        documentos_previos = [Documento(**d) for d in datos]
        print(f"{len(documentos_previos)} documentos previos cargados, no se vuelven a descargar")

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
    # ráfaga dura más que eso, aquí se reintenta la corrida completa
    # reanudando desde el último checkpoint en vez de perder todo el lote.
    documentos = documentos_previos
    intentos_agotados = 5
    for intento in range(1, intentos_agotados + 1):
        try:
            documentos = crawl(
                max_documentos=max_documentos,
                pausa_segundos=pausa,
                al_guardar=checkpoint,
                documentos_previos=documentos,
            )
            break
        except Exception as e:
            checkpoint(documentos)
            if intento == intentos_agotados:
                print(f"Se agotaron los {intentos_agotados} intentos, último error: {e}")
                raise
            espera = 30 * intento
            print(f"[intento {intento}/{intentos_agotados}] falló ({e}), reintentando en {espera}s...")
            time.sleep(espera)

    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
