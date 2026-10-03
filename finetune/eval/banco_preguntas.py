#!/usr/bin/env python3
"""Banco de preguntas al estilo QBR: consultas reales etiquetadas con sus documentos.

Idea (QBR, IJCAI 2025, arXiv 2505.04883): la distancia entre cómo pregunta la
gente y cómo está escrita la norma se puentea con un banco de preguntas de
personas comunes, cada una enlazada a lo que la responde. Al buscar, las
preguntas del banco parecidas a la nueva aportan sus documentos como una lista
más de candidatos, sin llamar a ningún modelo.

Aquí el banco sale de las 1.276 consultas reales cosechadas de Google
(`consultas_reales_google.json`), etiquetadas UNA vez con la búsqueda asistida
(Sonnet 5 reformula y reordena). Se mide sobre el piloto, cuyas consultas no
están en el banco.

Uso:
    .venv/Scripts/python.exe finetune/eval/banco_preguntas.py --etiquetar --muestra 180            # estima
    .venv/Scripts/python.exe finetune/eval/banco_preguntas.py --etiquetar --muestra 180 --ejecutar
    .venv/Scripts/python.exe finetune/eval/banco_preguntas.py --medir
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lab_recuperacion as lab  # noqa: E402

REALES = RAIZ / "finetune" / "eval" / "consultas_reales_google.json"
BANCO = RAIZ / "finetune" / "eval" / "banco_preguntas.json"
COSTO_POR_CONSULTA = 0.027  # medido el 3-oct con Sonnet 5 y 60 documentos
VECINOS = 3
DOCS_POR_PREGUNTA = 5


def etiquetar(muestra: int, ejecutar: bool) -> int:
    reales = json.loads(REALES.read_text(encoding="utf-8"))
    rng = random.Random(2026)
    elegidas = rng.sample(reales, min(muestra, len(reales)))
    banco: dict = json.loads(BANCO.read_text(encoding="utf-8")) if BANCO.exists() else {}
    pendientes = [r["consulta"] for r in elegidas if r["consulta"] not in banco]
    print(
        f"{len(pendientes)} consultas por etiquetar | estimado {len(pendientes) * COSTO_POR_CONSULTA:.2f} USD"
    )
    if not ejecutar:
        print("No se llamó a ninguna API. Añade --ejecutar.")
        return 0

    from finetune.clave_api import leer_clave
    from index.buscar import IndiceBusqueda
    from index.busqueda_asistida import buscar_asistida

    clave = leer_clave(obligatoria=True)
    ix = IndiceBusqueda()
    usd = 0.0
    for n, consulta in enumerate(pendientes, 1):
        try:
            r = buscar_asistida(ix, consulta, k=10, clave=clave)
        except Exception as e:  # noqa: BLE001 - una consulta fallida no tumba el lote
            print(f"  falló «{consulta[:40]}»: {type(e).__name__}", flush=True)
            continue
        usd += r.usd
        banco[consulta] = {
            "fragmentos": [x["id"] for x in r.resultados],
            "reformulaciones": r.reformulaciones,
        }
        BANCO.write_text(json.dumps(banco, ensure_ascii=False, indent=1), encoding="utf-8")
        if n % 20 == 0:
            print(f"  {n}/{len(pendientes)}  {usd:.2f} USD", flush=True)
    print(f"Costo real: {usd:.3f} USD. Banco: {len(banco)} preguntas.")
    return 0


def medir(umbral: float) -> int:
    from sentence_transformers import SentenceTransformer

    banco = json.loads(BANCO.read_text(encoding="utf-8"))
    preguntas = list(banco)
    cache = pickle.loads(lab.CACHE.read_bytes())
    casos = [c for c in lab.casos_anclados() if c["id"] in cache]
    reparto = lab.particion()
    m = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
    vb = m.encode(["query: " + p for p in preguntas], normalize_embeddings=True)
    vq = m.encode(["query: " + c["consulta"] for c in casos], normalize_embeddings=True)
    sim = vq @ vb.T

    filas = []
    for i, c in enumerate(casos):
        d = cache[c["id"]]
        vecinos = [j for j in sim[i].argsort()[::-1][:VECINOS] if sim[i][j] >= umbral]
        lista_banco = [f for j in vecinos for f in banco[preguntas[j]]["fragmentos"][:DOCS_POR_PREGUNTA]]
        base = lab.fusionar(d["vectorial"], d["fts"], 0.8)
        # La lista del banco entra con el peso de la vectorial (1,0) en el RRF.
        puntaje: dict[str, float] = {}
        for lista, peso in ((d["vectorial"], 1.0), (d["fts"], 0.8), (lista_banco, 1.0)):
            for rango, frag in enumerate(lista):
                puntaje[frag] = puntaje.get(frag, 0) + peso / (lab.K_RRF + rango)
        con_banco = [f for f, _ in sorted(puntaje.items(), key=lambda x: -x[1])]
        filas.append(
            {
                "sub": reparto.get(c["documento_id"]),
                "vecinos": len(vecinos),
                "base": lab.rango_documento(base, c["documento_id"]),
                "banco": lab.rango_documento(con_banco, c["documento_id"]),
            }
        )
    print(f"Banco: {len(preguntas)} preguntas | umbral de similitud {umbral} | {VECINOS} vecinos")
    print(f"Consultas del piloto con algún vecino: {sum(f['vecinos'] > 0 for f in filas)}/{len(filas)}")
    for sub in ("dev", "test", None):
        sel = [f for f in filas if sub is None or f["sub"] == sub]
        for k in ("base", "banco"):
            met = lab.metricas_rango([f[k] for f in sel])
            print(
                f"  {sub or 'todo':4} {k:6} recall@5 {met['recall@5'] * 100:5.1f}%"
                f"  mrr@10 {met['mrr@10']:.3f}"
            )
    gana = sum(1 for f in filas if (f["banco"] or 999) <= 5 < (f["base"] or 999))
    pierde = sum(1 for f in filas if (f["base"] or 999) <= 5 < (f["banco"] or 999))
    print(f"recall@5 frente a producción: gana {gana}, pierde {pierde}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--etiquetar", action="store_true")
    ap.add_argument("--muestra", type=int, default=180)
    ap.add_argument("--ejecutar", action="store_true")
    ap.add_argument("--medir", action="store_true")
    ap.add_argument("--umbral", type=float, default=0.85)
    a = ap.parse_args()
    if a.etiquetar:
        return etiquetar(a.muestra, a.ejecutar)
    if a.medir:
        return medir(a.umbral)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
