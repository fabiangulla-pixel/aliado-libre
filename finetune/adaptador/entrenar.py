"""Adaptador de CONSULTA: lleva el embedding de una pregunta coloquial hacia la
zona de los fragmentos legales, sin tocar el indice.

    q' = normalizar(q + q @ W)      W: 1024x1024, inicia en cero

Los vectores de los 3,3 M de fragmentos no cambian (nada que reindexar): solo
se transforma la consulta antes de la busqueda vectorial. Pares de
entrenamiento: las preguntas sinteticas de doc2query y su fragmento de origen.
Negativos: los demas fragmentos del lote + una muestra aleatoria del indice.

El embedding afinado del 3-oct se descarto (936 pares, reindexar, peor en dev).
Esto tiene ~30x mas pares y no reindexa. El riesgo es otro: que aprenda a
mandar TODO hacia las normas cubiertas (lo que paso con el peso 2 de la lista
de preguntas). Por eso se valida con NORMAS APARTADAS que no vio al entrenar.

    python finetune/adaptador/entrenar.py
    -> index/adaptador_consulta.npz  (W en float16)
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8")
SALIDA = RAIZ / "index" / "adaptador_consulta.npz"
SEMILLA = 13
NEGATIVOS_ALEATORIOS = 40_000
TEMPERATURA = 0.02
L2 = float(os.environ.get("ADAPTADOR_L2", "1e-3"))
EPOCAS = int(os.environ.get("ADAPTADOR_EPOCAS", "4"))


def _normalizar(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(1e-9)


def cargar() -> tuple[np.ndarray, list[str], dict[str, np.ndarray], np.ndarray]:
    import chromadb

    from index.buscar import COLECCION, DIR_INDICE

    d = np.load(RAIZ / "index" / "preguntas_sinteticas.npz")
    q = d["emb"].astype(np.float32)
    frags = [str(f) for f in d["fragmentos"]]
    col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    unicos = sorted(set(frags))
    pos = {}
    for i in range(0, len(unicos), 500):
        r = col.get(ids=unicos[i : i + 500], include=["embeddings"])
        for fid, e in zip(r["ids"], r["embeddings"], strict=True):
            pos[fid] = np.asarray(e, dtype=np.float32)
    total = col.count()
    rng = random.Random(SEMILLA)
    negs = []
    while sum(len(n) for n in negs) < NEGATIVOS_ALEATORIOS:
        r = col.get(limit=2000, offset=rng.randrange(0, total - 2000), include=["embeddings"])
        negs.append(
            np.asarray(
                [e for fid, e in zip(r["ids"], r["embeddings"], strict=True) if fid not in pos], np.float32
            )
        )
    print(
        f"{len(q)} preguntas, {len(pos)} fragmentos positivos, {sum(len(n) for n in negs)} negativos",
        flush=True,
    )
    return q, frags, pos, _normalizar(np.concatenate(negs))


def rango_medio(qs, objetivos, banco) -> tuple[float, float]:
    """recall@10 y rango mediano del fragmento correcto entre objetivos+banco."""
    cands = np.concatenate([objetivos, banco])
    sims = qs @ cands.T
    correcto = sims[np.arange(len(qs)), np.arange(len(qs))][:, None]  # objetivo i en la columna i
    rangos = (sims > correcto).sum(1)
    return float((rangos < 10).mean()), float(np.median(rangos))


def main() -> None:
    import torch

    torch.manual_seed(SEMILLA)
    q, frags, pos, banco = cargar()
    # negativos de validacion y de entrenamiento, disjuntos
    banco_val, banco = banco[:20000], banco[20000:]
    docs = sorted({f.split("::")[0] for f in frags})
    random.Random(SEMILLA).shuffle(docs)
    apartadas = set(docs[: max(3, len(docs) // 6)])  # normas que el adaptador NO ve
    ent = [i for i, f in enumerate(frags) if f.split("::")[0] not in apartadas and f in pos]
    val = [i for i, f in enumerate(frags) if f.split("::")[0] in apartadas and f in pos]
    print(f"normas apartadas para validar: {sorted(apartadas)}", flush=True)

    qn = _normalizar(q)
    pos_por_pregunta = _normalizar(np.stack([pos[frags[i]] for i in range(len(frags))]))

    def evaluar(W, indices, nombre):
        qs = qn[indices]
        if W is not None:
            qs = _normalizar(qs + qs @ W)
        # objetivos: un fragmento por pregunta (repetidos si varias preguntas comparten)
        r10, med = rango_medio(qs, pos_por_pregunta[indices], banco_val)
        print(f"  {nombre:28} recall@10 {r10 * 100:5.1f}%  rango mediano {med:.0f}", flush=True)
        return r10

    print("ANTES:", flush=True)
    evaluar(None, ent[:3000], "entrenamiento")
    base_val = evaluar(None, val, "NORMAS APARTADAS")

    W = torch.zeros(1024, 1024, requires_grad=True)
    opt = torch.optim.Adam([W], lr=1e-3)
    Q = torch.from_numpy(qn)
    P = torch.from_numpy(pos_por_pregunta)
    B = torch.from_numpy(banco)
    fid = np.array(frags)
    for epoca in range(EPOCAS):
        random.Random(SEMILLA + epoca).shuffle(ent)
        perdida_total = 0.0
        for i in range(0, len(ent), 256):
            lote = ent[i : i + 256]
            qb = Q[lote]
            qa = torch.nn.functional.normalize(qb + qb @ W, dim=1)
            negs = B[torch.randint(0, len(B), (4096,))]
            cands = torch.cat([P[lote], negs])
            logits = qa @ cands.T / TEMPERATURA
            # otra pregunta del lote con el MISMO fragmento no es negativo
            mismo = torch.from_numpy(fid[lote][:, None] == fid[lote][None, :])
            mismo.fill_diagonal_(False)
            logits[:, : len(lote)] = logits[:, : len(lote)].masked_fill(mismo, -1e4)
            perdida = torch.nn.functional.cross_entropy(logits, torch.arange(len(lote))) + L2 * (W**2).sum()
            opt.zero_grad()
            perdida.backward()
            opt.step()
            perdida_total += float(perdida)
        Wn = W.detach().numpy()
        print(f"epoca {epoca + 1}: perdida {perdida_total / (len(ent) / 256):.3f}", flush=True)
        evaluar(Wn, ent[:3000], "entrenamiento")
        v = evaluar(Wn, val, "NORMAS APARTADAS")
    np.savez(SALIDA, W=W.detach().numpy().astype(np.float16))
    veredicto = (
        "GENERALIZA" if v >= base_val + 0.02 else "NO generaliza: diferencia dentro del ruido (no adoptar)"
    )
    print(
        f"-> {SALIDA} | normas apartadas: {base_val * 100:.1f}% -> {v * 100:.1f}% | {veredicto}", flush=True
    )


if __name__ == "__main__":
    main()
