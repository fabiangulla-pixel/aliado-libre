#!/usr/bin/env python3
"""Banco de ensayos para arreglar la recuperación en lenguaje llano.

El piloto del 12-sep-2026 midió recall@5 del 61% para `abogado_junior` y del
**0%** para `adulto_mayor_informal` y `baja_alfabetizacion`. El sistema sirve a
quien ya sabe el vocabulario jurídico y falla con quien no. Esto existe para
arreglarlo midiendo, no adivinando.

Dos decisiones de método, las dos por lecciones caras del proyecto:

1. **Partición de desarrollo y prueba.** Ajustar un parámetro y reportarlo
   sobre las mismas consultas infla el resultado. Se parte por ancla (no por
   consulta) y estratificado por perfil, con semilla fija. Se ajusta en
   `dev` y solo al final se mira `test`.

2. **Se cachean los candidatos, no los resultados.** Las dos listas —vectorial
   y léxica— se piden UNA vez por consulta y se guardan. Barrer pesos de fusión
   después es aritmética sobre esas listas, así que una configuración nueva se
   evalúa en milisegundos en vez de reencodear 100 consultas. Sin esto, probar
   veinte configuraciones cuesta horas y se acaba probando tres.

Uso:
    ./.venv/Scripts/python.exe finetune/eval/lab_recuperacion.py --cachear
    ./.venv/Scripts/python.exe finetune/eval/lab_recuperacion.py --barrer-pesos
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

BANCO = RAIZ / "finetune" / "eval" / "banco_piloto_100.json"
CACHE = RAIZ / "finetune" / "eval" / "cache_candidatos.pkl"
PARTICION = RAIZ / "finetune" / "eval" / "particion_piloto.json"

TOPE = 5
K_RRF = 60
# Cuántos candidatos pedir a cada motor. Generoso a propósito: el cache se hace
# una vez y así se pueden probar ventanas más estrechas sin volver a pedir.
N_CANDIDATOS = 120


def casos_anclados() -> list[dict]:
    return [c for c in json.loads(BANCO.read_text(encoding="utf-8")) if c.get("documento_id")]


def particion() -> dict[str, str]:
    """Reparte las anclas en dev/test, estratificando por perfil.

    Se reparte por ANCLA y no por consulta para que ninguna necesidad de
    información quede a caballo entre las dos mitades: si el mismo documento
    aparece en dev y en test, ajustar en dev filtra información a test.
    """
    if PARTICION.exists():
        return json.loads(PARTICION.read_text(encoding="utf-8"))
    casos = casos_anclados()
    por_perfil: dict[str, list[str]] = defaultdict(list)
    for c in casos:
        por_perfil[c["perfil"]].append(c["documento_id"])

    rng = random.Random(2026)
    reparto: dict[str, str] = {}
    for _perfil, docs in sorted(por_perfil.items()):
        unicos = sorted(set(docs))
        rng.shuffle(unicos)
        corte = len(unicos) // 2
        for d in unicos[:corte]:
            reparto.setdefault(d, "dev")
        for d in unicos[corte:]:
            reparto.setdefault(d, "test")
    PARTICION.write_text(json.dumps(reparto, ensure_ascii=False, indent=1), encoding="utf-8")
    return reparto


def cachear() -> None:
    """Pide las dos listas de candidatos por consulta y las guarda."""
    from index.buscar import PREFIJO_CONSULTA, IndiceBusqueda, _consulta_fts, _tokenizar

    ix = IndiceBusqueda()
    casos = casos_anclados()
    print(f"Cacheando candidatos de {len(casos)} consultas (n={N_CANDIDATOS} por motor)...")

    datos = {}
    for i, c in enumerate(casos, 1):
        consulta = c["consulta"]
        emb = ix._modelo.encode([PREFIJO_CONSULTA + consulta]).tolist()
        vec = ix._coleccion.query(query_embeddings=emb, n_results=N_CANDIDATOS)["ids"][0]

        fts: list[str] = []
        tokens = _tokenizar(consulta)
        match = _consulta_fts(tokens)
        if ix._fts is not None and match:
            fts = [
                f[0]
                for f in ix._fts.execute(
                    "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (match, N_CANDIDATOS),
                ).fetchall()
            ]
        datos[c["id"]] = {"vectorial": vec, "fts": fts, "tokens": tokens}
        if i % 20 == 0:
            print(f"  {i}/{len(casos)}")

    CACHE.write_bytes(pickle.dumps(datos))
    print(f"Cache en {CACHE} ({CACHE.stat().st_size / 1e6:.1f} MB)")


def documento_de(frag_id: str) -> str:
    return frag_id.rsplit("::", 1)[0]


def fusionar(vec: list[str], fts: list[str], peso_bm25: float, peso_vec: float = 1.0) -> list[str]:
    puntaje: dict[str, float] = {}
    for rango, doc in enumerate(vec):
        puntaje[doc] = puntaje.get(doc, 0) + peso_vec / (K_RRF + rango)
    for rango, doc in enumerate(fts):
        puntaje[doc] = puntaje.get(doc, 0) + peso_bm25 / (K_RRF + rango)
    return [d for d, _ in sorted(puntaje.items(), key=lambda x: -x[1])]


def evaluar(cache, casos, config, subconjunto=None) -> dict:
    """Recall@5 global y por perfil para una configuración de fusión."""
    reparto = particion()
    aciertos: dict[str, list[bool]] = defaultdict(list)
    for c in casos:
        if subconjunto and reparto.get(c["documento_id"]) != subconjunto:
            continue
        d = cache.get(c["id"])
        if not d:
            continue
        orden = config(d)
        docs = [documento_de(x) for x in orden[:TOPE]]
        aciertos[c["perfil"]].append(c["documento_id"] in docs)
    todos = [a for v in aciertos.values() for a in v]
    return {
        "global": (sum(todos), len(todos)),
        "por_perfil": {p: (sum(v), len(v)) for p, v in aciertos.items()},
    }


def imprimir(nombre: str, r: dict) -> None:
    a, n = r["global"]
    print(f"\n{nombre}: {a}/{n} = {a / n * 100:.1f}%" if n else f"\n{nombre}: sin casos")
    for p, (pa, pn) in sorted(r["por_perfil"].items(), key=lambda x: -x[1][1]):
        print(f"    {p:24} {pa:>2}/{pn:<2} = {pa / pn * 100:5.1f}%")


def barrer_pesos() -> None:
    cache = pickle.loads(CACHE.read_bytes())
    casos = casos_anclados()
    print("=" * 72)
    print("BARRIDO DE LA FUSIÓN — solo sobre DESARROLLO")
    print("=" * 72)
    print("Hipótesis: con 0,8 la mitad léxica pesa casi tanto como la semántica,")
    print("y quien pregunta en lenguaje llano no comparte términos con la norma.")

    for nombre, peso in [
        ("solo vectorial", 0.0),
        ("bm25 0,2", 0.2),
        ("bm25 0,4", 0.4),
        ("bm25 0,8 (actual)", 0.8),
        ("bm25 1,5", 1.5),
        ("solo léxica", None),
    ]:
        if peso is None:
            cfg = lambda d: d["fts"]  # noqa: E731
        else:
            cfg = lambda d, p=peso: fusionar(d["vectorial"], d["fts"], p)  # noqa: E731
        imprimir(nombre, evaluar(cache, casos, cfg, "dev"))



def cachear_puente() -> None:
    """Cachea los candidatos con el puente de vocabulario, en sus dos formas.

    El puente (`finetune/lexico_curado.py`) se midio el 7-sep-2026 y se dio por
    NEUTRO. Pero se midio sobre el banco viejo, cuyas consultas nacian del
    fragmento que debian recuperar: ese banco no contenia el problema que el
    puente resuelve. Y se aplicaba **solo a la mitad lexica**, que segun el
    barrido de hoy apenas mueve el resultado.

    Aqui se prueban las dos formas por separado, que es la unica manera de
    saber cual de las dos cosas fallaba:
      lexico     traduce los tokens de la consulta FTS5 (lo ya probado)
      vectorial  anade los terminos juridicos al texto ANTES de embeberlo
    """
    from finetune.lexico_curado import expandir
    from index.buscar import PREFIJO_CONSULTA, IndiceBusqueda, _consulta_fts, _tokenizar

    ix = IndiceBusqueda()
    casos = casos_anclados()
    print(f"Cacheando variantes con puente de {len(casos)} consultas...")

    datos = {}
    for i, c in enumerate(casos, 1):
        consulta = c["consulta"]
        tokens = _tokenizar(consulta)
        tokens_puente = expandir(tokens)
        anadidos = [t for t in tokens_puente if t not in tokens]

        # Mitad lexica con los terminos traducidos
        fts_puente: list[str] = []
        match = _consulta_fts(tokens_puente)
        if ix._fts is not None and match:
            fts_puente = [
                f[0]
                for f in ix._fts.execute(
                    "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT ?",
                    (match, N_CANDIDATOS),
                ).fetchall()
            ]

        # Mitad vectorial con el texto ampliado: lo que NO se habia probado
        texto_ampliado = consulta + (" " + " ".join(anadidos) if anadidos else "")
        emb = ix._modelo.encode([PREFIJO_CONSULTA + texto_ampliado]).tolist()
        vec_puente = ix._coleccion.query(query_embeddings=emb, n_results=N_CANDIDATOS)["ids"][0]

        datos[c["id"]] = {
            "fts_puente": fts_puente,
            "vectorial_puente": vec_puente,
            "anadidos": anadidos,
        }
        if i % 20 == 0:
            print(f"  {i}/{len(casos)}")

    destino = CACHE.with_name("cache_puente.pkl")
    destino.write_bytes(pickle.dumps(datos))
    tocadas = sum(1 for d in datos.values() if d["anadidos"])
    print(f"Cache en {destino}. El puente toca {tocadas}/{len(datos)} consultas.")


def comparar_puente() -> None:
    base = pickle.loads(CACHE.read_bytes())
    pu = pickle.loads(CACHE.with_name("cache_puente.pkl").read_bytes())
    casos = casos_anclados()
    cache = {k: {**base[k], **pu.get(k, {})} for k in base}

    print("=" * 72)
    print("PUENTE DE VOCABULARIO - solo sobre DESARROLLO")
    print("=" * 72)
    tocadas = sum(1 for d in pu.values() if d["anadidos"])
    print(f"El puente toca {tocadas} de {len(pu)} consultas.")

    P = 0.8
    variantes = {
        "actual (sin puente)": lambda d: fusionar(d["vectorial"], d["fts"], P),
        "puente solo lexico": lambda d: fusionar(d["vectorial"], d.get("fts_puente", d["fts"]), P),
        "puente solo vectorial": lambda d: fusionar(d.get("vectorial_puente", d["vectorial"]), d["fts"], P),
        "puente en los dos": lambda d: fusionar(
            d.get("vectorial_puente", d["vectorial"]), d.get("fts_puente", d["fts"]), P
        ),
    }
    for nombre, cfg in variantes.items():
        imprimir(nombre, evaluar(cache, casos, cfg, "dev"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cachear", action="store_true")
    ap.add_argument("--barrer-pesos", action="store_true")
    ap.add_argument("--cachear-puente", action="store_true")
    ap.add_argument("--comparar-puente", action="store_true")
    a = ap.parse_args()
    if a.cachear:
        cachear()
    if a.barrer_pesos:
        if not CACHE.exists():
            print("Falta el cache: corre primero --cachear")
            return 1
        barrer_pesos()
    if a.cachear_puente:
        cachear_puente()
    if a.comparar_puente:
        comparar_puente()
    if not (a.cachear or a.barrer_pesos or a.cachear_puente or a.comparar_puente):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
