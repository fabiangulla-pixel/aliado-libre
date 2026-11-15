"""Crawl de sentencias de la Corte Suprema (salas Laboral y Civil), año por año.

Reanudable por dos vías: los fallos ya en data/raw/corte_suprema.json no se
vuelven a bajar, y los (sala, año) terminados quedan en
_corte_suprema_progreso.json y ni se listan. Pensado para dejarlo horas:

    .venv/Scripts/python.exe -u scripts/crawl_corte_suprema.py 200000 0.3
"""

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
# Con "_" delante: reindexar_con_gpu.py lee todo data/raw/*.json como documentos salvo esos.
PROGRESO = SALIDA.with_name("_corte_suprema_progreso.json")


def _escribir(ruta: Path, datos) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    def cargar_previos() -> list[Documento]:
        return (
            [Documento(**d) for d in json.loads(SALIDA.read_text(encoding="utf-8"))]
            if SALIDA.exists()
            else []
        )

    hechos = (
        {(s, a) for s, a in json.loads(PROGRESO.read_text(encoding="utf-8"))} if PROGRESO.exists() else set()
    )

    def checkpoint(documentos):
        _escribir(SALIDA, [d.to_dict() for d in documentos])
        print(f"[checkpoint] {len(documentos)} documentos", flush=True)

    def terminar_anio(sala, anio):
        hechos.add((sala, anio))
        _escribir(PROGRESO, sorted(hechos))
        print(f"[año completo] {sala} {anio}", flush=True)

    print(
        f"{len(cargar_previos())} previos, {len(hechos)} (sala, año) completos; objetivo {max_documentos}",
        flush=True,
    )
    documentos = crawl_con_reintentos(
        crawl,
        checkpoint,
        cargar_previos,
        intentos_agotados=20,
        max_documentos=max_documentos,
        pausa_segundos=pausa,
        anios_hechos=hechos,
        al_terminar_anio=terminar_anio,
    )
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
