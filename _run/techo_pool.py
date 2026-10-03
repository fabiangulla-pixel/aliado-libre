"""Techo del reordenamiento amplio segun el tamano del pool (gratis: reusa las
reformulaciones de Sonnet 5 guardadas y solo vuelve a buscar)."""

import json
import os
import pickle
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "finetune" / "eval"))
import lab_recuperacion as lab  # noqa: E402
import reordenar_amplio as ra  # noqa: E402

from index.buscar import PREFIJO_CONSULTA, IndiceBusqueda, _consulta_fts, _tokenizar  # noqa: E402

av = json.loads((ra.DIR_SALIDA / "avance_claude-sonnet-5.json").read_text(encoding="utf-8"))
cache = pickle.loads(lab.CACHE.read_bytes())
casos = [c for c in lab.casos_anclados() if c["id"] in av]
ix = IndiceBusqueda()


def motores(t, n):
    emb = ix._modelo.encode([PREFIJO_CONSULTA + t]).tolist()
    vec = ix._coleccion.query(query_embeddings=emb, n_results=n)["ids"][0]
    m = _consulta_fts(_tokenizar(t))
    fts = (
        [
            f[0]
            for f in ix._fts.execute(
                "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT ?", (m, n)
            ).fetchall()
        ]
        if m
        else []
    )
    return [vec, fts]


res = {}
for c in casos:
    d = cache[c["id"]]
    listas = [d["vectorial"], d["fts"]]
    for r in av[c["id"]]["reformulaciones"]:
        listas += motores(r, 300)
    orden = ra.candidatos_fusionados(listas)
    docs = ra.un_fragmento_por_documento(orden, 10**6)
    res[c["id"]] = lab.rango_documento(docs, c["documento_id"])
for k in (30, 60, 100, 150, 200, 300):
    print(f"pool {k:3} docs: techo {sum((r or 10**9) <= k for r in res.values())}/{len(res)}")
print("nunca aparece:", sum(r is None for r in res.values()))
pickle.dump(res, open(RAIZ / "_run" / "techo_pool.pkl", "wb"))
