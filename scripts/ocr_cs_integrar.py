"""Paso 3 del OCR de la Corte Suprema: convierte data/ocr_corte_suprema/
resultados*.jsonl en data/raw/corte_suprema_ocr.json, con el mismo formato que
corte_suprema.json, para que `reindexar_con_gpu.py --ampliar` lo recoja.

Se puede correr en cualquier momento, aunque el OCR no haya terminado: toma lo
que haya. Corre en el venv del proyecto.

    .venv\\Scripts\\python.exe scripts\\ocr_cs_integrar.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ingest.schema import Documento  # noqa: E402

CARPETA = RAIZ / "data" / "ocr_corte_suprema"
SALIDA = RAIZ / "data" / "raw" / "corte_suprema_ocr.json"
MOTOR = "PaddleOCR 3.7 (PP-OCRv5 mobile det, 200 dpi) en GPU"


def a_documento(r: dict) -> Documento:
    return Documento(
        id=r["id"],
        fuente="corte_suprema",
        tipo="sentencia",
        identificador=r["identificador"],
        titulo=f"Corte Suprema - Sala {r['sala']} - Sentencia {r['identificador']}",
        fecha=r["anio"],
        texto=r["texto"],
        url_original="https://consultaprovidencias.cortesuprema.gov.co/",
        metadata={
            "sala": r["sala"],
            "magistrado": r.get("magistrado"),
            "ruta": r["ruta"],
            "paginas": r.get("paginas"),
            "paginas_ocr": r.get("paginas_ocr"),
            "confianza_ocr": r.get("confianza"),
            "ocr": MOTOR if r.get("paginas_ocr") else None,
        },
    )


def main() -> None:
    previos = {d["id"] for d in json.loads((RAIZ / "data" / "raw" / "corte_suprema.json").read_text("utf-8"))}
    docs: dict[str, Documento] = {}
    for ruta in sorted(CARPETA.glob("resultados*.jsonl")):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(linea)
            except json.JSONDecodeError:
                continue  # línea a medias de un corte: la repara su trabajador al arrancar
            if r["id"] not in previos:
                docs[r["id"]] = a_documento(r)
    tmp = SALIDA.with_suffix(".tmp")
    tmp.write_text(json.dumps([d.to_dict() for d in docs.values()], ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(SALIDA)
    con_ocr = sum(1 for d in docs.values() if d.metadata["paginas_ocr"])
    print(f"{len(docs)} sentencias -> {SALIDA.name} ({con_ocr} con páginas pasadas por OCR)")


if __name__ == "__main__":
    main()
