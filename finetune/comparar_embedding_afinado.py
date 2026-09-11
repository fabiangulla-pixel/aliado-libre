#!/usr/bin/env python3
"""Compara el embedding base contra el afinado sin reindexar nada.

`candidatos_prueba.json` guarda, para cada una de las 200 consultas apartadas,
200 candidatos CON SU TEXTO. Reordenar ese mismo conjunto con cada embedding
mide cual coloca antes el documento correcto, en minutos en vez de en las 6
horas que cuesta reconstruir el indice.

Que mide y que no: el conjunto de candidatos lo recupero el sistema viejo, asi
que el techo esta limitado y el numero absoluto NO es comparable con el recall
del indice completo. Lo que si vale es la comparacion, porque ambos embeddings
ven exactamente el mismo conjunto. Si el afinado no gana aqui, no hay motivo
para gastar el reindexado.

Uso:
    ./.venv/Scripts/python.exe finetune/comparar_embedding_afinado.py
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CANDIDATOS = RAIZ / "finetune" / "eval" / "candidatos_prueba.json"
BASE = "intfloat/multilingual-e5-large"
AFINADO = RAIZ / "modelos" / "e5_afinado"
TOPES = (1, 5, 8)


def acierto(orden: list[dict], caso: dict, k: int) -> bool:
    for r in orden[:k]:
        if r.get("id") == caso["fragmento_id"]:
            return True
        if caso.get("documento_id") and r.get("documento_id") == caso["documento_id"]:
            return True
    return False


def evaluar(nombre: str, ruta: str, casos: list[dict]) -> dict[int, float]:
    from sentence_transformers import SentenceTransformer

    modelo = SentenceTransformer(ruta)
    modelo.max_seq_length = 512
    print(f"\n--- {nombre} ---", flush=True)

    aciertos = dict.fromkeys(TOPES, 0)
    detalle: dict[str, list[bool]] = defaultdict(list)
    for i, caso in enumerate(casos, 1):
        candidatos = caso["candidatos"]
        textos = ["passage: " + c.get("texto", "") for c in candidatos]
        vc = modelo.encode(textos, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        vq = modelo.encode(["query: " + caso["consulta"]], normalize_embeddings=True, show_progress_bar=False)
        puntajes = (vc @ vq[0]).tolist()
        orden = [c for _, c in sorted(zip(puntajes, candidatos, strict=True), key=lambda x: -x[0])]
        for k in TOPES:
            ok = acierto(orden, caso, k)
            aciertos[k] += ok
            if k == 5:
                detalle[caso["fragmento_id"]].append(ok)
        if i % 25 == 0:
            print(f"  [{i}/{len(casos)}] @5={aciertos[5] / i * 100:.0f}%", flush=True)

    n = len(casos)
    for k in TOPES:
        print(f"  recall@{k}: {aciertos[k]}/{n} = {aciertos[k] / n * 100:.1f}%")

    # Intervalo por conglomerados: el banco son 25 anclas x 8 perfiles, no 200
    # casos independientes.
    anclas = list(detalle.values())
    random.seed(7)
    muestras = []
    for _ in range(2000):
        elegidas = [random.choice(anclas) for _ in anclas]
        planas = [a for g in elegidas for a in g]
        muestras.append(sum(planas) / len(planas) * 100)
    muestras.sort()
    print(f"  IC 95% por {len(anclas)} anclas: {muestras[50]:.1f}% - {muestras[1949]:.1f}%")
    return {k: aciertos[k] / n * 100 for k in TOPES}, detalle


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limite", type=int, default=0)
    args = p.parse_args()

    casos = json.loads(CANDIDATOS.read_text(encoding="utf-8"))
    if args.limite:
        casos = casos[: args.limite]
    print(f"{len(casos)} consultas, {len(casos[0]['candidatos'])} candidatos cada una")

    if not AFINADO.exists():
        print(f"FALLO: no existe {AFINADO}. Correr antes afinar_embedding_local.py")
        return 1

    base, det_base = evaluar("EMBEDDING BASE", BASE, casos)
    fino, det_fino = evaluar("EMBEDDING AFINADO", str(AFINADO), casos)

    print("\n" + "=" * 60)
    print("COMPARACION (mismo conjunto de candidatos para los dos)")
    print("=" * 60)
    for k in TOPES:
        d = fino[k] - base[k]
        print(f"  recall@{k}: base {base[k]:5.1f}%  ->  afinado {fino[k]:5.1f}%   ({d:+.1f})")

    # McNemar por ancla, no por consulta: las 8 consultas de un ancla no son
    # observaciones independientes.
    gana = pierde = 0
    for ancla, vb in det_base.items():
        b, f = sum(vb), sum(det_fino.get(ancla, []))
        if f > b:
            gana += 1
        elif f < b:
            pierde += 1
    print(f"\n  anclas donde mejora: {gana} | donde empeora: {pierde} | de {len(det_base)}")
    print("\n  Decision: reindexar (6 h) solo si el afinado gana de forma clara.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
