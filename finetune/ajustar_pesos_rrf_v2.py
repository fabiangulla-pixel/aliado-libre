"""Recalibra el peso de BM25 frente al vectorial sobre el índice NUEVO.

Por qué hay que rehacerlo: `PESO_BM25 = 2.0` se fijó porque el embedding viejo
"casi no aportaba hallazgos únicos". Pero no aportaba nada **porque estaba
truncado a 128 tokens**: en el 76% de los fragmentos el vector solo
representaba el encabezado. Es decir, se calibró para compensar un defecto que
ya está corregido, y ahora ese peso ahoga justo la mitad que puede salvar la
distancia de vocabulario entre cómo pregunta un ciudadano y cómo escribe la
norma.

Método: se recuperan las dos listas (vectorial y léxica) UNA sola vez por
consulta y luego se fusionan en memoria con cada peso. Así probar veinte
combinaciones cuesta lo mismo que probar una.

Uso:
    ALIADO_COLECCION=... ALIADO_MODELO_EMBEDDINGS=... \
        ./venv/Scripts/python.exe finetune/ajustar_pesos_rrf_v2.py
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
PESOS = [0.0, 0.5, 0.9, 1.0, 1.1, 1.2, 1.25, 1.33, 1.4, 1.5, 2.0]  # peso de BM25; el vectorial es 1.0
K_MAX = 8


def _listas(indice, consulta: str, n: int) -> tuple[list[str], list[str], dict[str, str]]:
    """Las dos listas ordenadas por separado, sin fusionar."""
    from index import buscar as B

    emb = indice._modelo.encode([B.PREFIJO_CONSULTA + consulta]).tolist()
    vec = indice._coleccion.query(query_embeddings=emb, n_results=n)
    ids_vec = vec["ids"][0]

    ids_fts: list[str] = []
    if indice._fts is not None:
        match = B._consulta_fts(B._tokenizar(consulta))
        if match:
            cursor = indice._fts.execute(
                "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT ?",
                (match, n),
            )
            ids_fts = [f[0] for f in cursor.fetchall()]

    # El documento de CADA candidato, venga de la lista que venga. Construir este
    # mapa solo con los resultados vectoriales —como estaba antes— hacia que un
    # acierto encontrado solo por BM25 no pudiera contarse a nivel de documento:
    # la medicion penalizaba justo al lado cuyo peso se estaba evaluando.
    union = list(dict.fromkeys(ids_vec + ids_fts))
    documentos: dict[str, str] = {}
    if union:
        datos = indice._coleccion.get(ids=union, include=["metadatas"])
        for i, m in zip(datos["ids"], datos["metadatas"], strict=True):
            documentos[i] = (m or {}).get("documento_id")
    return ids_vec, ids_fts, documentos


def _fusionar(ids_vec: list[str], ids_fts: list[str], peso_bm25: float, k: int) -> list[str]:
    from index.buscar import K_RRF

    puntos: dict[str, float] = defaultdict(float)
    for rango, doc in enumerate(ids_vec):
        puntos[doc] += 1.0 / (K_RRF + rango)
    for rango, doc in enumerate(ids_fts):
        puntos[doc] += peso_bm25 / (K_RRF + rango)
    return [d for d, _ in sorted(puntos.items(), key=lambda x: -x[1])[:k]]


def _mcnemar(a: list[bool], b: list[bool]) -> float:
    sa = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    sb = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n, menor = sa + sb, min(sa, sb)
    if n == 0:
        return 1.0
    return min(sum(comb(n, i) for i in range(menor + 1)) / 2**n * 2, 1.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_dev.json"))
    p.add_argument("--por-perfil", type=int, default=25)
    args = p.parse_args()

    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    agrupado: dict[str, list] = defaultdict(list)
    for c in banco:
        agrupado[c["perfil"]].append(c)
    casos = [c for lista in agrupado.values() for c in lista[: args.por_perfil]]
    print(f"{len(casos)} consultas ({args.por_perfil} por perfil)")

    from index.buscar import COLECCION, MODELO_EMBEDDINGS, IndiceBusqueda

    print(f"modelo: {MODELO_EMBEDDINGS}\ncolección: {COLECCION}\nCargando índice...")
    t0 = time.time()
    indice = IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s\n")

    recuperado = []
    t0 = time.time()
    for i, caso in enumerate(casos, 1):
        recuperado.append(_listas(indice, caso["consulta"], K_MAX * 3))
        if i % 50 == 0:
            print(f"  {i}/{len(casos)}")
    print(f"recuperación hecha en {(time.time() - t0) / 60:.1f} min\n")

    def acierto(ids: list[str], caso: dict, documentos: dict) -> bool:
        if caso["fragmento_id"] in ids:
            return True
        doc = caso.get("documento_id")
        return bool(doc) and any(documentos.get(i) == doc for i in ids)

    tabla: dict[float, dict[int, list[bool]]] = {}
    perfiles: dict[float, dict[str, dict]] = {}
    for peso in PESOS:
        tabla[peso] = {k: [] for k in TOPES}
        agr: dict[str, dict] = defaultdict(lambda: {"total": 0, **dict.fromkeys(TOPES, 0)})
        for (ids_vec, ids_fts, documentos), caso in zip(recuperado, casos, strict=True):
            agr[caso["perfil"]]["total"] += 1
            for k in TOPES:
                ok = acierto(_fusionar(ids_vec, ids_fts, peso, k), caso, documentos)
                tabla[peso][k].append(ok)
                if ok:
                    agr[caso["perfil"]][k] += 1
        perfiles[peso] = dict(agr)

    n = len(casos)
    print("=" * 60)
    print(f"{'peso BM25':>10} " + " ".join(f"{'@' + str(k):>9}" for k in TOPES))
    for peso in PESOS:
        celdas = " ".join(f"{sum(tabla[peso][k]) / n * 100:8.1f}%" for k in TOPES)
        marca = "  <- actual" if peso == 2.0 else ""
        print(f"{peso:>10} {celdas}{marca}")

    mejor = max(PESOS, key=lambda w: sum(tabla[w][5]))
    print(f"\nMejor en @5: peso {mejor}")
    if mejor != 2.0:
        pv = _mcnemar(tabla[2.0][5], tabla[mejor][5])
        estado = "DIFERENCIA REAL" if pv < 0.05 else "no distinguible del ruido"
        print(f"  contra el actual (2.0): p={pv:.4f} -> {estado}")

    print(f"\nrecall@5 por perfil, actual (2.0) vs mejor ({mejor}):")
    print(f"  {'perfil':24} {'2.0':>7} {str(mejor):>8}")
    for perfil in sorted(perfiles[2.0]):
        a, b = perfiles[2.0][perfil], perfiles[mejor][perfil]
        print(f"  {perfil:24} {a[5] / a['total'] * 100:6.0f}% {b[5] / b['total'] * 100:7.0f}%")

    Path(RAIZ / "eval" / "pesos_rrf_v2.json").write_text(
        json.dumps(
            {
                "n": n,
                "modelo": MODELO_EMBEDDINGS,
                "coleccion": COLECCION,
                "por_peso": {str(w): {str(k): sum(tabla[w][k]) for k in TOPES} for w in PESOS},
                "por_perfil": {str(w): perfiles[w] for w in PESOS},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nDetalle en {RAIZ / 'eval' / 'pesos_rrf_v2.json'}")


if __name__ == "__main__":
    main()
