"""Mide si el reranker mejora la recuperación, y cuánto cuesta.

El reranker lee pregunta y pasaje JUNTOS, cosa que ni BM25 ni los embeddings
hacen: cada uno puntúa por separado y luego se fusionan. Debería atacar el fallo
dominante medido —elegir mal el pasaje entre los que sí llegaron— y sobre todo
mejorar el PRIMER resultado, que es el que más pesa para quien redacta después.

Se recuperan los candidatos una sola vez por consulta y luego se reordenan con
distintos tamaños de ventana, para no repetir la búsqueda por cada variante.

Uso:
    ./venv/Scripts/python.exe finetune/probar_reranker.py [--por-perfil 15]
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

TOPES = (1, 5, 8)
VENTANAS = (0, 10, 20, 40)  # 0 = sin reranker


def _acierto(items: list[dict], caso: dict, k: int) -> bool:
    for r in items[:k]:
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
    p.add_argument("--por-perfil", type=int, default=15)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_dev.json"))
    args = p.parse_args()

    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    agrupado: dict[str, list] = defaultdict(list)
    for c in banco:
        agrupado[c["perfil"]].append(c)
    casos = [c for lista in agrupado.values() for c in lista[: args.por_perfil]]
    print(f"{len(casos)} consultas ({args.por_perfil} por perfil)")

    from index.buscar import IndiceBusqueda
    from index.reordenar import MODELO_RERANKER, cargar_reranker

    print("Cargando índice...")
    t0 = time.time()
    indice = IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s")

    print(f"Cargando reranker ({MODELO_RERANKER})...")
    t0 = time.time()
    modelo = cargar_reranker()
    if modelo is None:
        raise SystemExit("El reranker no se pudo cargar.")
    print(f"listo en {time.time() - t0:.0f}s")

    print("Recuperando candidatos (una vez por consulta)...")
    candidatos = []
    t0 = time.time()
    for i, caso in enumerate(casos, 1):
        candidatos.append(indice.buscar(caso["consulta"], k=max(VENTANAS)))
        if i % 40 == 0:
            print(f"  {i}/{len(casos)}")
    print(f"recuperación: {(time.time() - t0) / len(casos):.2f} s/consulta\n")

    aciertos: dict[int, dict[int, list[bool]]] = {}
    tiempos: dict[int, float] = {}
    perfiles: dict[int, dict] = {}
    for ventana in VENTANAS:
        t0 = time.time()
        ordenados = []
        for caso, res in zip(casos, candidatos, strict=True):
            if ventana == 0:
                ordenados.append(res)
                continue
            trozo = res[:ventana]
            pares = [(caso["consulta"], (r.get("texto") or "")[:4000]) for r in trozo]
            puntajes = modelo.predict(pares)
            reordenado = [r for _, r in sorted(zip(puntajes, trozo, strict=True), key=lambda x: -x[0])]
            ordenados.append(reordenado + res[ventana:])
        tiempos[ventana] = (time.time() - t0) / len(casos)
        aciertos[ventana] = {
            k: [_acierto(o, c, k) for o, c in zip(ordenados, casos, strict=True)] for k in TOPES
        }
        agr: dict[str, dict] = defaultdict(lambda: {"total": 0, **dict.fromkeys(TOPES, 0)})
        for o, c in zip(ordenados, casos, strict=True):
            agr[c["perfil"]]["total"] += 1
            for k in TOPES:
                if _acierto(o, c, k):
                    agr[c["perfil"]][k] += 1
        perfiles[ventana] = dict(agr)
        print(f"  ventana {ventana or 'sin reranker':>13}: {tiempos[ventana]:.2f} s/consulta extra")

    n = len(casos)
    print("\n" + "=" * 62)
    print(f"{'ventana':>14} {'s/consulta':>11} " + " ".join(f"{'@' + str(k):>8}" for k in TOPES))
    for ventana in VENTANAS:
        etiqueta = "sin reranker" if ventana == 0 else f"top-{ventana}"
        celdas = " ".join(f"{sum(aciertos[ventana][k]) / n * 100:7.1f}%" for k in TOPES)
        print(f"{etiqueta:>14} {tiempos[ventana]:>10.2f}s {celdas}")

    print("\nContraste pareado contra 'sin reranker':")
    for ventana in VENTANAS[1:]:
        for k in TOPES:
            a, b, pv = _mcnemar(aciertos[0][k], aciertos[ventana][k])
            estado = "REAL" if pv < 0.05 else "ruido"
            print(f"  top-{ventana} @{k}: pierde {a}, gana {b}, p={pv:.4f} -> {estado}")

    mejor = max(VENTANAS[1:], key=lambda v: sum(aciertos[v][5]))
    print(f"\nrecall@5 por perfil, sin reranker vs top-{mejor}:")
    print(f"  {'perfil':24} {'sin':>7} {'con':>7}")
    for perfil in sorted(perfiles[0]):
        a, b = perfiles[0][perfil], perfiles[mejor][perfil]
        print(f"  {perfil:24} {a[5] / a['total'] * 100:6.0f}% {b[5] / b['total'] * 100:6.0f}%")

    Path(RAIZ / "eval" / "reranker.json").write_text(
        json.dumps(
            {
                "n": n,
                "modelo": MODELO_RERANKER,
                "por_ventana": {
                    str(v): {
                        "segundos": tiempos[v],
                        **{str(k): sum(aciertos[v][k]) for k in TOPES},
                    }
                    for v in VENTANAS
                },
                "por_perfil": {str(v): perfiles[v] for v in VENTANAS},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nDetalle en {RAIZ / 'eval' / 'reranker.json'}")


if __name__ == "__main__":
    main()
