"""Paso 1 del OCR de la Corte Suprema: lista las sentencias que el API publica y
que no están en data/raw/corte_suprema.json (casi todas PDF escaneados sin capa
de texto). Escribe data/ocr_corte_suprema/pendientes.jsonl, una por línea.

    .venv\\Scripts\\python.exe scripts\\ocr_cs_listar.py

Corre en el venv del proyecto. El OCR (paso 2) corre en el venv de Paddle:
scripts/ocr_cs_trabajador.py. Reanudable: los (sala, año) ya listados se saltan."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import requests  # noqa: E402

from ingest.fuentes import corte_suprema as cs  # noqa: E402

CARPETA = RAIZ / "data" / "ocr_corte_suprema"
PENDIENTES = CARPETA / "pendientes.jsonl"
HECHOS = CARPETA / "_listados.json"


def main() -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)
    corpus = json.loads((RAIZ / "data" / "raw" / "corte_suprema.json").read_text(encoding="utf-8"))
    tenemos = {d["id"] for d in corpus}
    hechos = set(map(tuple, json.loads(HECHOS.read_text(encoding="utf-8")))) if HECHOS.exists() else set()
    ya = set()
    if PENDIENTES.exists():
        ya = {json.loads(x)["id"] for x in PENDIENTES.read_text(encoding="utf-8").splitlines() if x}
    s = requests.Session()
    s.headers.update(cs.HEADERS)
    for sala in cs.SALAS:
        for anio in range(2026, cs.ANIO_MINIMO - 1, -1):
            if (sala, anio) in hechos:
                continue
            nuevos = 0
            with PENDIENTES.open("a", encoding="utf-8") as f:
                for item in cs._listar_anio(s, sala, anio, 0.05).values():
                    ident = cs._identificador_desde_titulo(item["title"])
                    id_ = f"corte_suprema:{sala.lower()}:{ident}"
                    if id_ in tenemos or id_ in ya:
                        continue
                    ya.add(id_)
                    fila = {
                        "id": id_,
                        "sala": sala,
                        "identificador": ident,
                        "anio": str(item.get("ano") or anio),
                        "magistrado": item.get("doctor"),
                        "ruta": item["onlinePath"],
                    }
                    f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                    nuevos += 1
            hechos.add((sala, anio))
            HECHOS.write_text(json.dumps(sorted(hechos)), encoding="utf-8")
            print(f"{sala} {anio}: {nuevos} pendientes", flush=True)
    print(f"TOTAL pendientes: {len(ya)}")


if __name__ == "__main__":
    main()
