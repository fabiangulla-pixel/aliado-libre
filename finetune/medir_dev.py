"""Medicion de desarrollo por la ruta real (IndiceBusqueda.buscar, reordenador en GPU).

Una configuracion por proceso: las variables ALIADO_* se leen al importar.
Guarda el resultado por caso para comparar configuraciones con McNemar.

    set ALIADO_RERANKER_DOCUMENTOS=120
    python finetune/medir_dev.py correr docs120            [banco: piloto por defecto]
    python finetune/medir_dev.py comparar base docs120

Siempre dos medidas (finetune/eval/acierto.py): exacta y equivalente.
Se elige con piloto (dev); banco_prueba_200 se mira UNA vez al final (D-06).
"""

from __future__ import annotations

import json
import os
import sys
import time
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("ALIADO_RERANKER_ACTIVO", "1")
sys.stdout.reconfigure(encoding="utf-8")

BANCOS = {"piloto": "banco_piloto_100.json", "prueba": "banco_prueba_200.json"}
CARPETA = RAIZ / "finetune" / "eval" / "dev"


def correr(etiqueta: str, banco: str = "piloto") -> None:
    from finetune.eval.acierto import posicion
    from index.buscar import IndiceBusqueda

    casos = [
        c
        for c in json.loads((RAIZ / "finetune" / "eval" / BANCOS[banco]).read_text(encoding="utf-8"))
        if c.get("documento_id")
    ]
    # MEDIR_EXPANSION=<json {consulta: texto_para_buscar}>: se busca con el
    # texto expandido (HyDE / Query2Doc) y se evalua contra el caso original.
    expansion = {}
    if os.environ.get("MEDIR_EXPANSION"):
        expansion = json.loads(Path(os.environ["MEDIR_EXPANSION"]).read_text(encoding="utf-8"))
    ix = IndiceBusqueda()
    ix.buscar("prueba de calentamiento", k=5)
    filas, t0 = [], time.time()
    for c in casos:
        t = time.time()
        res = ix.buscar(expansion.get(c["consulta"], c["consulta"]), k=5)
        filas.append(
            {
                "id": c.get("id") or c["consulta"][:60],
                "perfil": c.get("perfil"),
                "exacto": posicion(res, c),
                "equiv": posicion(res, c, equivalente=True),
                "uno": posicion(res[:1], c, equivalente=True),
                "s": round(time.time() - t, 3),
            }
        )
    n = len(filas)
    ex = sum(f["exacto"] is not None for f in filas)
    eq = sum(f["equiv"] is not None for f in filas)
    uno = sum(f["uno"] is not None for f in filas)
    config = {k: v for k, v in os.environ.items() if k.startswith(("ALIADO_", "MEDIR_"))}
    print(
        f"{etiqueta:14} {banco}: norma correcta #1 {uno / n * 100:5.1f}% | "
        f"recall@5 exacto {ex / n * 100:5.1f}% | equivalente {eq / n * 100:5.1f}% "
        f"| {(time.time() - t0) / n:.2f} s/consulta | {config}"
    )
    CARPETA.mkdir(parents=True, exist_ok=True)
    (CARPETA / f"{banco}_{etiqueta}.json").write_text(
        json.dumps({"config": config, "filas": filas}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def comparar(a: str, b: str, banco: str = "piloto") -> None:
    fa = {
        f["id"]: f for f in json.loads((CARPETA / f"{banco}_{a}.json").read_text(encoding="utf-8"))["filas"]
    }
    fb = {
        f["id"]: f for f in json.loads((CARPETA / f"{banco}_{b}.json").read_text(encoding="utf-8"))["filas"]
    }
    for medida in ("uno", "exacto", "equiv"):
        if any(medida not in f for f in list(fa.values()) + list(fb.values())):
            continue
        gana = sum(fa[i][medida] is None and fb[i][medida] is not None for i in fa)
        pierde = sum(fa[i][medida] is not None and fb[i][medida] is None for i in fa)
        print(f"{a} -> {b} [{medida}]: gana {gana}, pierde {pierde}, McNemar p={mcnemar(gana, pierde):.3f}")


if __name__ == "__main__":
    accion = sys.argv[1]
    if accion == "correr":
        correr(sys.argv[2], *(sys.argv[3:4]))
    elif accion == "comparar":
        comparar(sys.argv[2], sys.argv[3], *(sys.argv[4:5]))
