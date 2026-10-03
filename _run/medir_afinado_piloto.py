#!/usr/bin/env python3
"""Embedding base contra afinado sobre el piloto de 100 consultas, sin reindexar.

El 12-sep se midio el afinado sobre `banco_prueba_200` (25 anclas reformuladas
8 veces) y salio indistinguible del azar. El piloto tiene anclas independientes:
mas potencia para la misma pregunta.

Metodo: para cada consulta se toma la union de los candidatos cacheados
(vectorial + lexica, `cache_candidatos.pkl`), se leen sus textos del indice y
se reordenan con cada embedding. Ambos modelos ven el mismo conjunto, asi que
la comparacion vale aunque el techo lo ponga el buscador actual (sesgo a favor
del base: los candidatos vectoriales los eligio el). Se informa reordenado puro
y fusionado con la mitad lexica como en produccion (RRF, BM25 0,8).

Los pares de entrenamiento no comparten positivos ni consultas con el piloto
(comprobado el 3-oct-2026: 0 de 72 documentos; 6 aparecen solo como negativos).
"""

from __future__ import annotations

import os
import pickle
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "finetune" / "eval"))

import lab_recuperacion as L  # noqa: E402

MODELOS = {"base": "intfloat/multilingual-e5-large", "afinado": str(RAIZ / "modelos" / "e5_afinado")}


def main() -> int:
    import chromadb
    from sentence_transformers import SentenceTransformer

    cache = pickle.loads(L.CACHE.read_bytes())
    casos = [c for c in L.casos_anclados() if c["id"] in cache]
    reparto = L.particion()

    col = chromadb.PersistentClient(str(RAIZ / "index" / "chroma_db")).get_collection(
        "aliado_libre_multilingual_e5_large"
    )
    ids = sorted({i for d in cache.values() for i in d["vectorial"] + d["fts"]})
    textos: dict[str, str] = {}
    for j in range(0, len(ids), 500):
        r = col.get(ids=ids[j : j + 500], include=["documents"])
        textos.update(zip(r["ids"], r["documents"], strict=True))
    print(f"{len(casos)} consultas, {len(textos)} fragmentos candidatos")

    rangos: dict[str, dict[str, dict[str, int | None]]] = defaultdict(dict)
    for nombre, ruta in MODELOS.items():
        m = SentenceTransformer(ruta, device="cuda")
        m.max_seq_length = 512
        unicos = list(textos)
        vecs = m.encode(
            ["passage: " + (textos[i] or "") for i in unicos],
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        v_de = dict(zip(unicos, vecs, strict=True))
        for c in casos:
            d = cache[c["id"]]
            cand = [i for i in dict.fromkeys(d["vectorial"] + d["fts"]) if i in v_de]
            q = m.encode(["query: " + c["consulta"]], normalize_embeddings=True)[0]
            orden = [i for _, i in sorted((-float(v_de[i] @ q), i) for i in cand)]
            rangos[nombre + " puro"][c["id"]] = L.rango_documento(orden, c["documento_id"])
            fus = L.fusionar(orden[: L.N_CANDIDATOS], d["fts"], 0.8)
            rangos[nombre + " +lexica"][c["id"]] = L.rango_documento(fus, c["documento_id"])
        del m

    for sub in ("dev", "test", None):
        print(f"\n=== {sub or 'todo'} ===")
        sel = [c for c in casos if sub is None or reparto.get(c["documento_id"]) == sub]
        for var, r in rangos.items():
            met = L.metricas_rango([r[c["id"]] for c in sel])
            print(
                f"  {var:18} recall@5 {met['recall@5'] * 100:5.1f}%  recall@10 {met['recall@10'] * 100:5.1f}%"
                f"  mrr@10 {met['mrr@10']:.3f}  (n={len(sel)})"
            )

    for modo in ("puro", "+lexica"):
        gana = pierde = 0
        for c in casos:
            b = (rangos[f"base {modo}"][c["id"]] or 999) <= 5
            a = (rangos[f"afinado {modo}"][c["id"]] or 999) <= 5
            gana += a and not b
            pierde += b and not a
        print(f"\n{modo}: afinado gana {gana}, pierde {pierde} (recall@5, todo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
