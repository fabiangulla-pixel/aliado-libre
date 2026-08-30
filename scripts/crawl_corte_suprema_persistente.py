"""Igual que crawl_corte_suprema.py, pero para dejar corriendo sin
supervisión mientras el backend recupera estabilidad: en vez de darse por
vencido tras 5 intentos, chequea /filters antes de cada intento (barato,
GET simple) y sigue reintentando indefinidamente con pausas largas entre
ráfagas, hasta completar max_documentos o agotar los intentos totales
(por defecto muy alto — pensado para dejarlo horas, no minutos)."""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import requests
import urllib3

warnings.filterwarnings("ignore")
urllib3.disable_warnings()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.corte_suprema import crawl
from ingest.schema import Documento

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "corte_suprema.json"
FILTERS_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/filters"
PAUSA_ENTRE_RAFAGAS = 300  # 5 min entre ráfagas cuando el backend está caído


def backend_esta_sano() -> bool:
    try:
        r = requests.get(FILTERS_URL, verify=False, timeout=15)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 2.5
    rafagas_maximas = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    documentos: list[Documento] = []
    if SALIDA.exists():
        datos = json.loads(SALIDA.read_text(encoding="utf-8"))
        documentos = [Documento(**d) for d in datos]
        print(f"{len(documentos)} documentos previos cargados, no se vuelven a descargar", flush=True)

    def checkpoint(docs):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in docs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(docs)} documentos guardados en {SALIDA}", flush=True)

    print(f"Objetivo: {max_documentos} documentos, hasta {rafagas_maximas} ráfagas", flush=True)

    for rafaga in range(1, rafagas_maximas + 1):
        if len(documentos) >= max_documentos:
            break

        if not backend_esta_sano():
            print(
                f"[ráfaga {rafaga}/{rafagas_maximas}] backend caído (/filters no responde 200), "
                f"esperando {PAUSA_ENTRE_RAFAGAS}s...",
                flush=True,
            )
            time.sleep(PAUSA_ENTRE_RAFAGAS)
            continue

        print(f"[ráfaga {rafaga}/{rafagas_maximas}] backend sano, intentando crawl...", flush=True)
        try:
            documentos = crawl(
                max_documentos=max_documentos,
                pausa_segundos=pausa,
                al_guardar=checkpoint,
                documentos_previos=documentos,
            )
        except Exception as e:
            checkpoint(documentos)
            print(
                f"[ráfaga {rafaga}/{rafagas_maximas}] falló ({e}), "
                f"esperando {PAUSA_ENTRE_RAFAGAS}s antes de reintentar...",
                flush=True,
            )
            time.sleep(PAUSA_ENTRE_RAFAGAS)

    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
