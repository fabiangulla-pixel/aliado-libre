#!/usr/bin/env python3
"""Compara embeddings sobre el piloto sin reindexar (mismo metodo que
medir_afinado_piloto.py): se reordena la union de candidatos cacheados
(vectorial + lexica) con cada modelo. Sesgo a favor del e5 base: los
candidatos vectoriales los eligio el.

Uso: .venv/Scripts/python.exe _run/medir_embedding_piloto.py
"""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "0"  # la primera vez hay que bajar los modelos
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "finetune" / "eval"))

import lab_recuperacion as L  # noqa: E402

# nombre: (ruta, prefijo/prompt de consulta, prefijo de pasaje)
MODELOS = {
    "e5-large (produccion)": ("intfloat/multilingual-e5-large", {"prefijo": "query: "}, "passage: "),
    "ALIA-MrBERT legal": (
        "SINAI/ALIA-MrBERT-es-legal-administrative-embeddings",
        {"prompt_name": "query"},
        "",
    ),
}


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
    print(f"{len(casos)} consultas, {len(textos)} fragmentos", flush=True)

    rangos: dict[str, dict] = {}
    for nombre, (ruta, consulta_cfg, pref_pasaje) in MODELOS.items():
        m = SentenceTransformer(ruta, device="cuda", trust_remote_code=True)
        m.max_seq_length = 512
        unicos = list(textos)
        vecs = m.encode(
            [pref_pasaje + (textos[i] or "") for i in unicos],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        v_de = dict(zip(unicos, vecs, strict=True))
        puro, mixto = {}, {}
        for c in casos:
            d = cache[c["id"]]
            cand = [i for i in dict.fromkeys(d["vectorial"] + d["fts"]) if i in v_de]
            if "prompt_name" in consulta_cfg:
                q = m.encode(
                    [c["consulta"]], prompt_name=consulta_cfg["prompt_name"], normalize_embeddings=True
                )[0]
            else:
                q = m.encode([consulta_cfg["prefijo"] + c["consulta"]], normalize_embeddings=True)[0]
            orden = [i for _, i in sorted((-float(v_de[i] @ q), i) for i in cand)]
            puro[c["id"]] = L.rango_documento(orden, c["documento_id"])
            mixto[c["id"]] = L.rango_documento(
                L.fusionar(orden[: L.N_CANDIDATOS], d["fts"], 0.8), c["documento_id"]
            )
        rangos[nombre + " puro"] = puro
        rangos[nombre + " +lexica"] = mixto
        del m
        print(f"listo {nombre}", flush=True)

    for sub in ("dev", "test", None):
        print(f"\n=== {sub or 'todo'} ===")
        sel = [c for c in casos if sub is None or reparto.get(c["documento_id"]) == sub]
        for var, r in rangos.items():
            met = L.metricas_rango([r[c["id"]] for c in sel])
            print(
                f"  {var:32} recall@5 {met['recall@5'] * 100:5.1f}%  recall@10 {met['recall@10'] * 100:5.1f}%"
                f"  mrr@10 {met['mrr@10']:.3f}"
            )
    base = rangos["e5-large (produccion) puro"]
    otro = rangos["ALIA-MrBERT legal puro"]
    gana = sum(1 for c in casos if (otro[c["id"]] or 999) <= 5 < (base[c["id"]] or 999))
    pierde = sum(1 for c in casos if (base[c["id"]] or 999) <= 5 < (otro[c["id"]] or 999))
    print(f"\nALIA puro frente a e5 puro (recall@5): gana {gana}, pierde {pierde}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
