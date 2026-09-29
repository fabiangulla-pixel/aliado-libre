"""Construye `index/vigencia_documentos.json`: el estado de vigencia de cada
documento cuya nota oficial lo declara derogado, inexequible, revocado…

Recorre el índice FTS5 completo (el texto de todos los fragmentos) porque la
nota de un documento derogado suele estar solo en sus primeros fragmentos. Ver
`index/vigencia.py`.

Uso:  .venv/Scripts/python.exe -m index.build_vigencia
"""

from __future__ import annotations

import collections
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from index.buscar import DB_FTS  # noqa: E402
from index.vigencia import RUTA_TABLA, construir_tabla, indexar_suin  # noqa: E402

# Catálogo de SUIN-Juriscol: scripts/descargar_suin_vigencias.py
RUTA_SUIN = Path(__file__).resolve().parent.parent / "data" / "suin_vigencias.json"


def main() -> None:
    conexion = sqlite3.connect(f"file:{DB_FTS}?mode=ro", uri=True)
    total = conexion.execute("SELECT count(*) FROM fragmentos_fts").fetchone()[0]
    filas = conexion.execute("SELECT id, texto FROM fragmentos_fts")
    suin = None
    if RUTA_SUIN.exists():
        suin = indexar_suin(json.loads(RUTA_SUIN.read_text(encoding="utf-8")))
        print(f"SUIN-Juriscol: {len(suin)} normas con vigencia utilizable")
    else:
        print(f"AVISO: sin {RUTA_SUIN}; solo se leen las notas del texto.")
    tabla = construir_tabla(filas, suin)
    documentos = len({i.split("::", 1)[0] for (i,) in conexion.execute("SELECT id FROM fragmentos_fts")})
    salida = {
        "construida": date.today().isoformat(),
        "fragmentos_leidos": total,
        "suin": RUTA_SUIN.name if suin else None,
        "documentos_en_indice": documentos,
        "por_estado": dict(collections.Counter(v["estado"] for v in tabla.values())),
        "documentos": tabla,
    }
    RUTA_TABLA.write_text(json.dumps(salida, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(tabla)} de {documentos} documentos con nota de vigencia -> {RUTA_TABLA}")
    print(salida["por_estado"])


if __name__ == "__main__":
    main()
