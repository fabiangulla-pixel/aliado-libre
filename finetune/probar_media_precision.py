#!/usr/bin/env python3
"""Mide si codificar el indice en fp16 va mas rapido y ordena igual.

El reindexado codifica en fp32 y tarda ~6 horas. El proyecto ya midio que el
RERANKER en fp16 ordena identico y va 2,9x mas rapido, pero eso NO se puede dar
por bueno aqui: un cross-encoder puntua pares y un bi-encoder produce vectores
que luego se comparan por coseno, y ahi los errores de redondeo se acumulan
distinto. Asi que se comprueba.

Criterio de adopcion: el top-5 tiene que coincidir en el mismo orden en
practicamente todas las consultas. Si no coincide, se queda en fp32 aunque sea
mas lento: un indice mas rapido que ordena distinto es un indice distinto.

Uso:
    ./.venv/Scripts/python.exe finetune/probar_media_precision.py
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CANDIDATOS = RAIZ / "finetune" / "eval" / "candidatos_prueba.json"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--modelo", default="")
    p.add_argument("--pasajes", type=int, default=3000)
    p.add_argument("--consultas", type=int, default=60)
    args = p.parse_args()

    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    from index.buscar import MODELO_EMBEDDINGS, PREFIJO_CONSULTA, PREFIJO_PASAJE

    ruta = args.modelo or MODELO_EMBEDDINGS
    print(f"modelo: {ruta}")
    print(f"prefijos: consulta={PREFIJO_CONSULTA!r} pasaje={PREFIJO_PASAJE!r}")

    casos = json.loads(CANDIDATOS.read_text(encoding="utf-8"))
    random.seed(7)
    consultas = [c["consulta"] for c in casos[: args.consultas]]
    textos: list[str] = []
    for c in casos:
        for cand in c["candidatos"]:
            t = cand.get("texto", "")
            if t:
                textos.append(t)
        if len(textos) >= args.pasajes:
            break
    textos = textos[: args.pasajes]
    print(f"{len(textos)} pasajes, {len(consultas)} consultas\n")

    def codificar(media: bool):
        modelo = SentenceTransformer(ruta)
        modelo.max_seq_length = 512
        if media:
            modelo = modelo.half()
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        v = modelo.encode(
            [PREFIJO_PASAJE + t for t in textos],
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        torch.cuda.synchronize()
        tardo = time.perf_counter() - t0
        vq = modelo.encode(
            [PREFIJO_CONSULTA + c for c in consultas],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        del modelo
        torch.cuda.empty_cache()
        return np.asarray(v, dtype=np.float32), np.asarray(vq, dtype=np.float32), tardo

    print("codificando en fp32...", flush=True)
    v32, q32, t32 = codificar(False)
    print(f"  {t32:.1f} s  ({len(textos) / t32:.0f} pasajes/s)")

    print("codificando en fp16...", flush=True)
    v16, _, t16 = codificar(True)
    print(f"  {t16:.1f} s  ({len(textos) / t16:.0f} pasajes/s)")

    print(f"\nfp16 es {t32 / t16:.2f}x mas rapido")

    # Las consultas se codifican SIEMPRE en fp32 (es como corre la busqueda),
    # y solo cambia la precision de los pasajes del indice: ese es el escenario
    # real que se estaria adoptando.
    iguales_top1 = iguales_top5 = 0
    for i in range(len(consultas)):
        o32 = np.argsort(-(v32 @ q32[i]))[:5]
        o16 = np.argsort(-(v16 @ q32[i]))[:5]
        iguales_top1 += int(o32[0] == o16[0])
        iguales_top5 += int(list(o32) == list(o16))

    n = len(consultas)
    print(f"\nmismo top-1:            {iguales_top1}/{n} ({iguales_top1 / n * 100:.0f}%)")
    print(f"mismo top-5 y en orden: {iguales_top5}/{n} ({iguales_top5 / n * 100:.0f}%)")

    if iguales_top5 == n:
        print("\nADOPTAR fp16: ordena identico y es mas rapido.")
        return 0
    print("\nNO adoptar fp16: ordena distinto. Un indice mas rapido que ordena")
    print("distinto es un indice distinto, y habria que volver a medirlo todo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
