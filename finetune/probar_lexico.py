"""¿Sube el acierto si traducimos la consulta al vocabulario de la norma?

Se compara la búsqueda de hoy contra la misma búsqueda con la consulta léxica
expandida por el puente curado (`finetune/lexico_curado.py`). Solo se toca la
mitad léxica: la vectorial recibe la consulta original, porque el embedding ya
trabaja por significado y meterle términos añadidos lo despista — es lo que
mató a HyDE.

Se mide sobre la partición de PRUEBA, que no se usó para escribir el puente.

Uso:
    ./venv/Scripts/python.exe finetune/probar_lexico.py [--por-perfil 25]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

from finetune.lexico_curado import expandir  # noqa: E402

TOPES = (1, 5, 8)


def _acierto(resultados: list[dict], caso: dict, k: int) -> bool:
    for r in resultados[:k]:
        if r.get("id") == caso["fragmento_id"]:
            return True
        if caso.get("documento_id") and r.get("documento_id") == caso["documento_id"]:
            return True
    return False


def _mcnemar(a: list[bool], b: list[bool]) -> tuple[int, int, float]:
    sa = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    sb = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n, menor = sa + sb, min(sa, sb)
    if n == 0:
        return sa, sb, 1.0
    return sa, sb, min(sum(comb(n, i) for i in range(menor + 1)) / 2**n * 2, 1.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--por-perfil", type=int, default=25)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_prueba.json"))
    p.add_argument("--salida", default=str(RAIZ / "eval" / "lexico_resultado.json"))
    args = p.parse_args()

    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    agrupado: dict[str, list] = defaultdict(list)
    for c in banco:
        agrupado[c["perfil"]].append(c)
    casos = [c for lista in agrupado.values() for c in lista[: args.por_perfil]]
    print(f"{len(casos)} consultas apartadas")

    import index.buscar as buscar

    print("Cargando índice...")
    t0 = time.time()
    indice = buscar.IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s")

    tokenizar_original = buscar._tokenizar
    tocadas = 0

    def tokenizar_expandido(texto: str) -> list[str]:
        nonlocal tocadas
        tokens = tokenizar_original(texto)
        ampliados = expandir(tokens)
        if len(ampliados) > len(tokens):
            tocadas += 1
        return ampliados

    aciertos = {"actual": {k: [] for k in TOPES}, "puente": {k: [] for k in TOPES}}
    t0 = time.time()
    for i, caso in enumerate(casos, 1):
        buscar._tokenizar = tokenizar_original
        res_actual = indice.buscar(caso["consulta"], k=max(TOPES))
        buscar._tokenizar = tokenizar_expandido
        res_puente = indice.buscar(caso["consulta"], k=max(TOPES))
        for modo, res in (("actual", res_actual), ("puente", res_puente)):
            for k in TOPES:
                aciertos[modo][k].append(_acierto(res, caso, k))
        if i % 50 == 0:
            print(f"  {i}/{len(casos)} — {(time.time() - t0) / i:.1f} s/consulta")
    buscar._tokenizar = tokenizar_original

    n = len(casos)
    print(f"\nEl puente añadió términos en {tocadas} de {n * 2} búsquedas expandidas")
    print(f"\n{'modo':>8} " + " ".join(f"{'@' + str(k):>8}" for k in TOPES))
    for modo in ("actual", "puente"):
        celdas = " ".join(f"{sum(aciertos[modo][k]) / n * 100:7.1f}%" for k in TOPES)
        print(f"{modo:>8} {celdas}")
    print("\nContraste pareado:")
    for k in TOPES:
        pierde, gana, pv = _mcnemar(aciertos["actual"][k], aciertos["puente"][k])
        print(f"  @{k}: pierde {pierde:2}, gana {gana:2}, p={pv:.4f} -> {'REAL' if pv < 0.05 else 'ruido'}")
    Path(args.salida).write_text(
        json.dumps(
            {
                "n": n,
                "consultas_tocadas": tocadas,
                "aciertos": {m: {str(k): sum(v[k]) for k in TOPES} for m, v in aciertos.items()},
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
