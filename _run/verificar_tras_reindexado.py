#!/usr/bin/env python3
"""Verifica el indice recien construido y mide si de verdad sirve.

Se corre cuando reindexar_con_gpu.py termina con codigo 0. Compara contra las
dos referencias medidas sobre el mismo banco: 33,5% el indice sano viejo y 0,5%
el indice roto del 9-sep-2026.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

REFERENCIAS = {"indice sano viejo (7-sep)": 33.5, "indice roto (9-sep)": 0.5}
BANCO = RAIZ / "finetune" / "eval" / "banco_prueba_200.json"
DETALLE = RAIZ / "finetune" / "eval" / "recall_indice_nuevo.json"


def intervalo_por_conglomerados() -> None:
    """Remuestrea por fragmento ancla, no por consulta.

    El banco son 25 fragmentos ancla reformulados en 8 perfiles de usuario cada
    uno: 200 consultas, pero solo 25 necesidades de informacion independientes.
    Un intervalo calculado como si hubiera 200 casos sale demasiado estrecho, y
    un McNemar que supone pares independientes exagera la significancia. Vale
    igual para las cifras historicas (33,5% y el "+10 puntos del reranker").
    """
    if not (DETALLE.exists() and BANCO.exists()):
        print("  (falta el detalle o el banco: no se calcula el intervalo)")
        return
    datos = json.loads(DETALLE.read_text(encoding="utf-8"))
    casos = datos.get("detalle", [])
    ancla_de = {b["consulta"]: b["fragmento_id"] for b in json.loads(BANCO.read_text(encoding="utf-8"))}

    grupos: dict[str, list[bool]] = defaultdict(list)
    for c in casos:
        ancla = ancla_de.get(c.get("pregunta"))
        if ancla is not None and "acierto@5" in c:
            grupos[ancla].append(bool(c["acierto@5"]))
    if not grupos:
        print("  (no se pudo unir el detalle con el banco)")
        return

    anclas = list(grupos.values())
    random.seed(7)
    muestras = []
    for _ in range(2000):
        elegidas = [random.choice(anclas) for _ in anclas]
        planas = [a for grupo in elegidas for a in grupo]
        muestras.append(sum(planas) / len(planas) * 100)
    muestras.sort()
    aciertos = sum(a for g in anclas for a in g)
    consultas = sum(len(g) for g in anclas)
    print()
    print(f"Recall@5 = {aciertos / consultas * 100:.1f}%  ({aciertos}/{consultas})")
    print(f"  IC 95% por {len(anclas)} anclas: {muestras[50]:.1f}% - {muestras[1949]:.1f}%")
    print("  El banco son 25 anclas x 8 perfiles: tratarlo como n=200 estrecha el intervalo de mas.")
    for nombre, valor in REFERENCIAS.items():
        print(f"  referencia {nombre}: {valor}%")


def main() -> int:
    import chromadb

    from index.buscar import COLECCION, DB_FTS, DIR_INDICE, IndiceBusqueda

    print("=" * 70)
    print("VERIFICACION DEL INDICE RECONSTRUIDO")
    print("=" * 70)

    if not DIR_INDICE.exists():
        print("FALLO: no existe el indice de Chroma")
        return 1
    coleccion = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    total = coleccion.count()
    print(f"Chroma: {total} fragmentos")
    if total < 900_000:
        print("  AVISO: por debajo de los 928.086 que anuncio el reindexado")

    if not DB_FTS.exists():
        print("FALLO: no existe el indice lexico FTS5; la busqueda pierde su mitad lexica")
        return 1
    with sqlite3.connect(f"file:{DB_FTS}?mode=ro", uri=True) as con:
        filas = con.execute("SELECT count(*) FROM fragmentos_fts").fetchone()[0]
    print(f"FTS5: {filas} filas")
    if abs(filas - total) > total * 0.01:
        print(f"  AVISO: FTS5 y Chroma no cuadran ({filas} vs {total})")

    print()
    print("Prueba de cordura: buscar un fragmento por su propio texto...")
    muestra = coleccion.get(limit=1, include=["documents"])
    texto = (muestra["documents"][0] or "")[:200]
    resultados = IndiceBusqueda().buscar(texto, k=5)
    ids = [r.get("id") for r in resultados]
    if muestra["ids"][0] in ids:
        print(f"  OK: se encuentra a si mismo (posicion {ids.index(muestra['ids'][0]) + 1})")
    else:
        print("  FALLO: un fragmento no se encuentra ni con su propio texto")

    print()
    print("=" * 70)
    print("RECALL SOBRE LAS 200 CONSULTAS APARTADAS")
    print("=" * 70, flush=True)
    salida = subprocess.run(
        [
            sys.executable,
            str(RAIZ / "finetune" / "medir_recuperacion.py"),
            "--banco",
            str(BANCO),
            "--salida",
            str(DETALLE),
        ],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
    )
    print("\n".join(x for x in salida.stdout.splitlines() if "it/s" not in x))
    if salida.returncode != 0:
        print("La medicion fallo:", salida.stderr[-2000:])
        return 1
    intervalo_por_conglomerados()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
