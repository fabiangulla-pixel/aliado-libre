"""Crawl del Consejo de Estado recorriendo los números de relatoría (NR).

Reanudable: los documentos ya en data/raw/consejo_estado.json se conservan y el
último NR recorrido queda en data/raw/_consejo_estado_progreso.json ("_" para que
reindexar_con_gpu.py no lo lea como documentos).

    .venv/Scripts/python.exe -u scripts/crawl_consejo_estado.py 500000 0.1
"""

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
from ingest.fuentes.consejo_estado import crawl
from ingest.schema import Documento
from scripts._crawl_retry import crawl_con_reintentos

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "consejo_estado.json"
PROGRESO = SALIDA.with_name("_consejo_estado_progreso.json")


def _escribir(ruta: Path, datos) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def _leer_progreso() -> int:
    return json.loads(PROGRESO.read_text(encoding="utf-8"))["ultimo_nr"] + 1 if PROGRESO.exists() else 0


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    def cargar_previos() -> list[Documento]:
        if not SALIDA.exists():
            return []
        return [Documento(**d) for d in json.loads(SALIDA.read_text(encoding="utf-8"))]

    # El JSON llega a GB: se escribe cada pocos minutos, no en cada lote. El
    # progreso se anota solo junto a una escritura y con el NR del lote anterior
    # (crawl llama al_guardar antes que al_avanzar), así nunca apunta más allá de
    # lo que ya está en disco.
    estado = {"ultimo_visto": None, "ultima_escritura": 0.0}

    def checkpoint(documentos, forzar: bool = False):
        if not forzar and time.monotonic() - estado["ultima_escritura"] < 600:
            return
        _escribir(SALIDA, [d.to_dict() for d in documentos])
        if estado["ultimo_visto"] is not None:
            _escribir(PROGRESO, {"ultimo_nr": estado["ultimo_visto"]})
        estado["ultima_escritura"] = time.monotonic()
        print(f"[checkpoint] {len(documentos)} documentos, NR {estado['ultimo_visto']}", flush=True)

    def avanzar(nr: int) -> None:
        estado["ultimo_visto"] = nr

    def crawl_desde_progreso(**kwargs):
        return crawl(desde_nr=_leer_progreso(), **kwargs)

    print(
        f"{len(cargar_previos())} previos; reanuda en NR {_leer_progreso()}; objetivo {max_documentos}",
        flush=True,
    )
    documentos = crawl_con_reintentos(
        crawl_desde_progreso,
        checkpoint,
        cargar_previos,
        intentos_agotados=20,
        max_documentos=max_documentos,
        pausa_segundos=pausa,
        al_avanzar=avanzar,
    )
    checkpoint(documentos, forzar=True)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
