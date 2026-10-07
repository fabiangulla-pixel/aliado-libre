"""Aplica `ingest/anonimizar.py` a los conceptos ya descargados en data/raw.

El ingester ya enmascara al descargar; esto es para lo bajado antes de que
existiera la regla. Idempotente: correrlo dos veces no cambia nada más.

Uso:
    .venv/Scripts/python.exe scripts/anonimizar_raw.py superservicios supersalud
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ingest.anonimizar import enmascarar_destinatario  # noqa: E402


def main() -> None:
    for fuente in sys.argv[1:]:
        ruta = RAIZ / "data" / "raw" / f"{fuente}.json"
        docs = json.loads(ruta.read_text(encoding="utf-8"))
        cambiados: list[str] = []
        for d in docs:
            nuevo = enmascarar_destinatario(d["texto"])
            if nuevo != d["texto"]:
                d["texto"] = nuevo
                cambiados.append(d["id"])
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(ruta)
        # Los documentos cambiados hay que re-codificarlos: el índice guarda el texto viejo.
        registro = RAIZ / "_run" / f"anonimizados_{fuente}.json"
        registro.write_text(json.dumps(cambiados, ensure_ascii=False), encoding="utf-8")
        print(f"{fuente}: {len(cambiados)} de {len(docs)} documentos enmascarados -> {registro.name}")


if __name__ == "__main__":
    main()
