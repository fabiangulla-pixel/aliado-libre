"""Prueba si elegir los términos por frecuencia en el corpus mejora la búsqueda.

El problema encontrado midiendo: `_tokenizar` se queda con los **primeros** 12
términos útiles. En una consulta con ruido —"Mire doctor yo soy de Tunja tengo
45 años y estoy desesperado…"— esos 12 primeros son todo el preámbulo personal,
y la pregunta jurídica, que viene al final, nunca llega a la búsqueda. Ese
perfil mide 0% de acierto, con el índice viejo y con el nuevo.

La idea: elegir los términos por su frecuencia en el corpus, con una **banda**.
No vale ordenar por rareza a secas: "desesperado" aparece en 2 de 718.388
fragmentos, así que sería el término más "informativo" y arrastraría esos dos
fragmentos irrelevantes al primer puesto. Con `OR`, un término rarísimo domina
el ranking.

- Demasiado común (>25% del corpus): no discrimina y es el más caro de buscar.
- Demasiado raro (<5 fragmentos): no puede ser el tema de la consulta; son
  nombres propios, ciudades o erratas, y su peso distorsiona el ranking.
- Lo de en medio: se conservan hasta MAX, empezando por los más específicos.

Uso:
    ./venv/Scripts/python.exe finetune/probar_tokenizacion.py [--por-perfil 20]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

TOPES = (1, 5, 8)
TOTAL_FRAGMENTOS = 718388
DF_MAXIMA = 0.25 * TOTAL_FRAGMENTOS  # por encima de esto no discrimina
DF_MINIMA = 5  # por debajo, solo puede traer ruido
MAX_TERMINOS = 12


def _sin_tildes(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def hacer_tokenizador_por_frecuencia(ruta_fts: Path, vacias: frozenset):
    """Devuelve un tokenizador que elige por frecuencia, con su propia conexión."""
    con = sqlite3.connect(f"file:{ruta_fts}?mode=ro", uri=True)
    con.execute("CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main,'fragmentos_fts','row')")
    cache: dict[str, int] = {}

    def df(termino: str) -> int:
        if termino not in cache:
            fila = con.execute("SELECT doc FROM temp.vocab WHERE term=?", (termino,)).fetchone()
            cache[termino] = fila[0] if fila else 0
        return cache[termino]

    def tokenizar(texto: str) -> list[str]:
        crudos = re.findall(r"\w+", _sin_tildes(texto))
        vistos: set[str] = set()
        candidatos: list[tuple[int, str]] = []
        for token in crudos:
            if len(token) <= 2 or token in vacias or token in vistos:
                continue
            vistos.add(token)
            frecuencia = df(token)
            if frecuencia < DF_MINIMA or frecuencia > DF_MAXIMA:
                continue
            candidatos.append((frecuencia, token))
        if not candidatos:
            # sin nada en la banda, mejor buscar mal que no buscar
            return [t for t in crudos if len(t) > 2 and t not in vacias][:MAX_TERMINOS]
        # los más específicos primero: dentro de la banda, menos frecuente = más
        # informativo
        candidatos.sort(key=lambda x: x[0])
        return [t for _, t in candidatos[:MAX_TERMINOS]]

    return tokenizar


def _acierto(resultados: list[dict], caso: dict, k: int) -> bool:
    for r in resultados[:k]:
        if r.get("id") == caso["fragmento_id"]:
            return True
        if caso.get("documento_id") and r.get("documento_id") == caso["documento_id"]:
            return True
    return False


def _mcnemar(a: list[bool], b: list[bool]) -> tuple[int, int, float]:
    solo_a = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    solo_b = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n, menor = solo_a + solo_b, min(solo_a, solo_b)
    if n == 0:
        return solo_a, solo_b, 1.0
    return solo_a, solo_b, min(sum(comb(n, i) for i in range(menor + 1)) / 2**n * 2, 1.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--por-perfil", type=int, default=20)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_dev.json"))
    args = p.parse_args()

    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    agrupado: dict[str, list] = defaultdict(list)
    for c in banco:
        agrupado[c["perfil"]].append(c)
    casos = [c for lista in agrupado.values() for c in lista[: args.por_perfil]]
    print(f"{len(casos)} consultas ({args.por_perfil} por perfil)")

    from index import buscar as B

    por_posicion = B._tokenizar
    por_frecuencia = hacer_tokenizador_por_frecuencia(B.DB_FTS, B.PALABRAS_VACIAS)

    print("Cargando índice...")
    t0 = time.time()
    indice = B.IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s")

    resultados: dict[str, dict] = {}
    aciertos: dict[str, dict[int, list[bool]]] = {}
    for etiqueta, tokenizador in (("por posición", por_posicion), ("por frecuencia", por_frecuencia)):
        B._tokenizar = tokenizador
        filas = []
        t0 = time.time()
        for caso in casos:
            filas.append(indice.buscar(caso["consulta"], k=max(TOPES)))
        segundos = (time.time() - t0) / len(casos)
        aciertos[etiqueta] = {
            k: [_acierto(f, c, k) for f, c in zip(filas, casos, strict=True)] for k in TOPES
        }
        perfiles: dict[str, dict] = defaultdict(lambda: {"total": 0, **dict.fromkeys(TOPES, 0)})
        for f, c in zip(filas, casos, strict=True):
            perfiles[c["perfil"]]["total"] += 1
            for k in TOPES:
                if _acierto(f, c, k):
                    perfiles[c["perfil"]][k] += 1
        resultados[etiqueta] = {"segundos": segundos, "perfiles": dict(perfiles)}
        print(f"  [{etiqueta}] {segundos:.2f} s/consulta")

    B._tokenizar = por_posicion

    print("\n" + "=" * 60)
    print(f"{'tokenización':16} {'s/consulta':>11} " + " ".join(f"{'@' + str(k):>8}" for k in TOPES))
    for etiqueta in resultados:
        celdas = " ".join(f"{sum(aciertos[etiqueta][k]) / len(casos) * 100:7.1f}%" for k in TOPES)
        print(f"{etiqueta:16} {resultados[etiqueta]['segundos']:>10.2f}s {celdas}")

    print("\nContraste pareado (McNemar exacto):")
    for k in TOPES:
        a, b, pv = _mcnemar(aciertos["por posición"][k], aciertos["por frecuencia"][k])
        estado = "DIFERENCIA REAL" if pv < 0.05 else "no distinguible del ruido"
        print(f"  @{k}: solo posición {a}, solo frecuencia {b}, p={pv:.4f} -> {estado}")

    print("\nrecall@5 por perfil:")
    print(f"  {'perfil':24} {'posición':>10} {'frecuencia':>11}")
    for perfil in sorted(resultados["por posición"]["perfiles"]):
        a = resultados["por posición"]["perfiles"][perfil]
        b = resultados["por frecuencia"]["perfiles"][perfil]
        print(f"  {perfil:24} {a[5] / a['total'] * 100:9.0f}% {b[5] / b['total'] * 100:10.0f}%")


if __name__ == "__main__":
    main()
