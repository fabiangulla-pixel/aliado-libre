#!/usr/bin/env python3
"""¿El reordenador destilado mejora la búsqueda 100% local? Sobre datos apartados.

Compara, en la MISMA máquina y la misma corrida (regla D-07):
  - hoy: la fusión RRF de producción, sin reordenar;
  - bge: bge-reranker-v2-m3 sin afinar sobre un pool diversificado;
  - destilado: el mismo modelo afinado con las elecciones de Sonnet.
El pool es un fragmento por documento de la búsqueda local (POOL documentos):
exactamente lo que el alumno verá en producción, sin ninguna IA de nube.

Bancos (ninguno se usó para entrenar):
  - piloto: las 95 consultas ancladas (`lab_recuperacion`), candidatos del cache;
  - prueba_200: `banco_prueba_200.json`, 25 por perfil, candidatos en vivo.
Reporta recall@k por ancla, por perfil, McNemar contra hoy, y guarda el top-10
de cada sistema del piloto en `finetune/eval/sistemas_locales/` para que el juez
de pertinencia (`juez_fable.py`) los califique.

Uso:
    .venv/Scripts/python.exe finetune/destilar/evaluar_reordenador.py
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import time
from math import comb
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "finetune" / "eval"))

import lab_recuperacion as lab  # noqa: E402
import reordenar_amplio as ra  # noqa: E402

POOL = int(os.environ.get("ALIADO_POOL_DESTILADO", "150"))
MAX_CARACTERES = 2000
DESTILADO = RAIZ / "modelos" / "reranker_destilado"
DIR_SISTEMAS = RAIZ / "finetune" / "eval" / "sistemas_locales"


def mcnemar(a: list[bool], b: list[bool]) -> tuple[int, int, float]:
    pierde = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    gana = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n = pierde + gana
    if n == 0:
        return pierde, gana, 1.0
    return pierde, gana, min(sum(comb(n, i) for i in range(min(pierde, gana) + 1)) / 2**n * 2, 1.0)


def main() -> int:
    import chromadb
    from sentence_transformers.cross_encoder import CrossEncoder

    from index.buscar import (
        COLECCION,
        DIR_INDICE,
        PREFIJO_CONSULTA,
        IndiceBusqueda,
        _consulta_fts,
        _tokenizar,
    )

    col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    modelos = {"bge": CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)}
    if DESTILADO.exists():
        modelos["destilado"] = CrossEncoder(str(DESTILADO), max_length=512)
    for m in modelos.values():
        m.model.half()

    cache_textos: dict[str, str] = {}

    def textos(ids: list[str]) -> dict[str, str]:
        faltan = [i for i in ids if i not in cache_textos]
        if faltan:
            datos = col.get(ids=faltan, include=["documents", "metadatas"])
            for fid, doc, meta in zip(datos["ids"], datos["documents"], datos["metadatas"], strict=True):
                cache_textos[fid] = f"{(meta or {}).get('titulo_documento') or ''}\n{doc or ''}"[
                    :MAX_CARACTERES
                ]
        return {i: cache_textos[i] for i in ids if i in cache_textos}

    def ordenar(nombre: str, consulta: str, orden: list[str]) -> list[str]:
        if nombre == "hoy":
            return orden
        pool = ra.un_fragmento_por_documento(orden, POOL)
        tx = textos(pool)
        pool = [f for f in pool if f in tx]
        p = modelos[nombre].predict([(consulta, tx[f]) for f in pool], batch_size=64)
        return [f for _, f in sorted(zip(p, pool, strict=True), key=lambda x: -x[0])]

    sistemas = ["hoy", *modelos]

    def evaluar(nombre_banco: str, casos: list[dict], orden_de) -> None:
        aciertos = {s: {k: [] for k in (1, 5, 10)} for s in sistemas}
        perfiles = []
        tops = {s: {} for s in sistemas}
        t0 = time.time()
        for c in casos:
            orden = orden_de(c)
            perfiles.append(c.get("perfil", "?"))
            for s in sistemas:
                res = ordenar(s, c["consulta"], orden)
                tops[s][c.get("id", c["consulta"])] = res[:10]
                r = lab.rango_documento(res, c["documento_id"])
                for k in (1, 5, 10):
                    aciertos[s][k].append(r is not None and r <= k)
        n = len(casos)
        print(f"\n=== {nombre_banco} (n={n}, pool {POOL} documentos, {time.time() - t0:.0f}s) ===")
        print(f"{'sistema':12} " + " ".join(f"{'@' + str(k):>7}" for k in (1, 5, 10)))
        for s in sistemas:
            print(f"{s:12} " + " ".join(f"{sum(aciertos[s][k]) / n * 100:6.1f}%" for k in (1, 5, 10)))
        print("por perfil (@5):")
        for perfil in sorted(set(perfiles)):
            idx = [i for i, p in enumerate(perfiles) if p == perfil]
            celdas = "  ".join(f"{s} {sum(aciertos[s][5][i] for i in idx):2}" for s in sistemas)
            print(f"  {perfil:26} n={len(idx):2}  {celdas}")
        for s in sistemas[1:]:
            pierde, gana, pv = mcnemar(aciertos["hoy"][5], aciertos[s][5])
            print(f"  McNemar @5 hoy vs {s}: pierde {pierde}, gana {gana}, p={pv:.4f}")
        if nombre_banco == "piloto":
            DIR_SISTEMAS.mkdir(exist_ok=True)
            for s in sistemas[1:]:
                (DIR_SISTEMAS / f"local_{s}_pool{POOL}.json").write_text(
                    json.dumps(tops[s], ensure_ascii=False), encoding="utf-8"
                )

    # piloto: candidatos del cache (índice actual)
    cache = pickle.loads(lab.CACHE.read_bytes())
    piloto = [c for c in lab.casos_anclados() if c["id"] in cache]
    evaluar("piloto", piloto, lambda c: lab.fusionar(cache[c["id"]]["vectorial"], cache[c["id"]]["fts"], 0.8))

    # prueba_200: candidatos en vivo
    ix = IndiceBusqueda()

    def en_vivo(c: dict) -> list[str]:
        emb = ix._modelo.encode([PREFIJO_CONSULTA + c["consulta"]]).tolist()
        vec = ix._coleccion.query(query_embeddings=emb, n_results=120)["ids"][0]
        match = _consulta_fts(_tokenizar(c["consulta"]))
        fts = []
        if ix._fts is not None and match:
            fts = [
                f[0]
                for f in ix._fts.execute(
                    "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT 120",
                    (match,),
                ).fetchall()
            ]
        return lab.fusionar(vec, fts, 0.8)

    prueba = [
        c
        for c in json.loads(
            (RAIZ / "finetune" / "eval" / "banco_prueba_200.json").read_text(encoding="utf-8")
        )
        if c.get("documento_id")
    ]
    evaluar("prueba_200", prueba, en_vivo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
