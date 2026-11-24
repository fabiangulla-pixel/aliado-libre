"""Experimento (dev, piloto): ¿no promover la ley general cuando el #1 de la
busqueda ya es un documento especifico que la aplica?

Gratis: usa las sugerencias de gemma4:26b ya cacheadas
(finetune/eval/expansion/piloto_norma_gemma4_26b.json); solo corre la fusion.

    set ALIADO_MODO_ORDEN=fusion & set ALIADO_PESO_PREGUNTAS=1
    python _run/exp_no_promover.py
"""

from __future__ import annotations

import json
import os
import sys
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("ALIADO_MODO_ORDEN", "fusion")
os.environ.setdefault("ALIADO_PESO_PREGUNTAS", "1")
sys.stdout.reconfigure(encoding="utf-8")

from finetune.eval.acierto import posicion  # noqa: E402
from index.buscar import (  # noqa: E402
    CANDIDATOS_FUSION,
    FUENTES_JUDICIALES,
    IndiceBusqueda,
    limitar_sentencias,
    un_fragmento_por_documento,
)
from index.normas import norma, norma_de_resultado, normas  # noqa: E402

BANCO = sys.argv[1] if len(sys.argv) > 1 else "piloto"
ARCH = {"piloto": "banco_piloto_100.json"}[BANCO]
CACHE = RAIZ / "finetune" / "eval" / "expansion" / f"{BANCO}_norma_gemma4_26b.json"


def fuente(r):
    return (r.get("id") or r.get("documento_id") or "").split(":", 1)[0]


def menciona(r, n):
    return n in normas((r.get("titulo_documento") or "") + " " + (r.get("texto") or ""))


def reglas(docs, sug):
    """Devuelve {variante: nuevo orden}."""
    out = {"fusion": docs}
    idx = next((i for i, r in enumerate(docs) if norma_de_resultado(r) == sug), None) if sug else None
    if idx is None or idx == 0:
        for v in ("actual", "R1", "R2", "R3"):
            out[v] = docs
        return out, idx
    promovido = [docs[idx]] + docs[:idx] + docs[idx + 1 :]
    out["actual"] = promovido
    top = docs[0]
    es_norma_top = norma_de_resultado(top) is not None
    no_judicial = fuente(top) not in FUENTES_JUDICIALES
    # R1: el #1 menciona la norma sugerida -> se queda
    out["R1"] = docs if menciona(top, sug) else promovido
    # R2: R1 solo si el #1 no es sentencia
    out["R2"] = docs if (menciona(top, sug) and no_judicial) else promovido
    # R3: R2 y ademas el #1 es otra norma (decreto/resolucion) o concepto que la cita
    out["R3"] = docs if (menciona(top, sug) and no_judicial and not es_norma_top) else promovido
    return out, idx


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2**n)


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    casos = [
        c
        for c in json.loads((RAIZ / "finetune" / "eval" / ARCH).read_text(encoding="utf-8"))
        if c.get("documento_id")
    ]
    ix = IndiceBusqueda()
    res: dict[str, list] = {}
    detalle = []
    for c in casos:
        crudos = ix._buscar_crudo(c["consulta"], k=CANDIDATOS_FUSION)
        docs = un_fragmento_por_documento(crudos)
        sug = norma(cache.get(c["consulta"]) or "")
        variantes, idx = reglas(docs, sug)
        fila = {
            "consulta": c["consulta"][:80],
            "sug": sug,
            "idx": idx,
            "top": docs[0].get("titulo_documento", "")[:80] if docs else "",
        }
        for v, orden in variantes.items():
            salida = limitar_sentencias(orden, 5)
            ok = posicion(salida[:1], c, equivalente=True) is not None
            res.setdefault(v, []).append(ok)
            fila[v] = ok
        detalle.append(fila)
    n = len(casos)
    for v, oks in res.items():
        print(f"{v:7} #1 {sum(oks)}/{n} = {sum(oks) / n * 100:.1f}%")
    base = res["actual"]
    for v in ("R1", "R2", "R3"):
        g = sum((not a) and b for a, b in zip(base, res[v], strict=True))
        p = sum(a and (not b) for a, b in zip(base, res[v], strict=True))
        print(f"actual -> {v}: gana {g}, pierde {p}, McNemar p={mcnemar(g, p):.3f}")
    for f in detalle:
        if f["actual"] != f["R1"] or f["actual"] != f["R3"]:
            print(f"  {'+' if f['R3'] else '-'} {f['consulta']} | top: {f['top']} | sug {f['sug']}")
    (RAIZ / "_run" / f"exp_no_promover_{BANCO}.json").write_text(
        json.dumps(detalle, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
