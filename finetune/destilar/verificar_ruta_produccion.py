#!/usr/bin/env python3
"""La mejora medida, ¿le llega al usuario? Mide por `IndiceBusqueda.buscar()`.

`evaluar_reordenador.py` reordena a mano sobre los candidatos; aquí se usa la
misma función que llaman la GUI, el MCP y `responder`, con el reordenador
apagado y encendido, sobre el banco prueba_200. Si las cifras no se parecen a las
de la evaluación, algo del cableado no replica lo medido.

Uso:
    .venv/Scripts/python.exe finetune/destilar/verificar_ruta_produccion.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))


def main() -> int:
    import index.reordenar as R
    from index.buscar import IndiceBusqueda

    casos = [
        c
        for c in json.loads(
            (RAIZ / "finetune" / "eval" / "banco_prueba_200.json").read_text(encoding="utf-8")
        )
        if c.get("documento_id")
    ]
    ix = IndiceBusqueda()
    print(f"modelo del reordenador: {R.MODELO_RERANKER}")
    for estado in ("0", "1"):
        os.environ["ALIADO_RERANKER_ACTIVO"] = estado
        aciertos, t0 = 0, time.time()
        for c in casos:
            res = ix.buscar(c["consulta"], k=5)
            aciertos += any(r.get("documento_id") == c["documento_id"] for r in res)
        n = len(casos)
        print(
            f"reordenador {'encendido' if estado == '1' else 'apagado '}: recall@5 {aciertos / n * 100:.1f}% "
            f"({aciertos}/{n}) | {(time.time() - t0) / n:.2f} s/consulta"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
