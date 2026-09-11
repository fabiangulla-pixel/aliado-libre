#!/usr/bin/env python3
"""Afina el embedding e5-large en la GPU local, sin Colab.

Traslada `colab_afinar_embedding.ipynb` a esta maquina (RTX 5080, 16 GB). El
notebook existia porque el PC viejo no daba; ya no hace falta.

Comprobado antes de escribir esto: los 936 pares salen de 118 documentos ancla y
**ninguno** coincide con los 24 del banco de prueba, ni se repite una sola
consulta. Afinar con esto y medir contra `banco_prueba_200.json` no filtra.

Uso:
    ./.venv/Scripts/python.exe finetune/afinar_embedding_local.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "0")  # hay que bajar el modelo base la 1a vez

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PARES = RAIZ / "finetune" / "data" / "pares_embedding.jsonl"
SALIDA = RAIZ / "modelos" / "e5_afinado"
BASE = "intfloat/multilingual-e5-large"
JUEZ = "BAAI/bge-reranker-v2-m3"
UMBRAL = 0.95  # un negativo que puntue por encima del 95% del positivo es sospechoso


def limpiar_negativos_falsos(registros: list[dict]) -> list[dict]:
    """Quita los negativos que en realidad responden la consulta.

    Los negativos se sacaron de los primeros resultados de la busqueda, que son
    justo los mas propensos a ser relevantes sin estar etiquetados. Entrenar con
    ellos le ensena al modelo a ALEJAR documentos que si responden. En MS-MARCO
    se estima ~70% de contaminacion; la auditoria de este proyecto dio 78%.
    """
    from sentence_transformers import CrossEncoder

    juez = CrossEncoder(JUEZ, max_length=512, device="cuda")
    limpios, descartados, sin_negativos = [], 0, 0
    for i, d in enumerate(registros, 1):
        pares = [[d["consulta"], d["positivo"]]] + [[d["consulta"], n] for n in d["negativos"]]
        puntajes = juez.predict(pares, batch_size=64, show_progress_bar=False)
        corte = puntajes[0] * UMBRAL if puntajes[0] > 0 else puntajes[0] / UMBRAL
        buenos = [n for n, s in zip(d["negativos"], puntajes[1:], strict=True) if s < corte]
        descartados += len(d["negativos"]) - len(buenos)
        if not buenos:
            sin_negativos += 1
            continue
        limpios.append({**d, "negativos": buenos})
        if i % 100 == 0:
            print(f"  limpiados {i}/{len(registros)}", flush=True)

    total = sum(len(d["negativos"]) for d in registros)
    print(f"negativos originales: {total}")
    print(f"  descartados por falsos: {descartados} ({descartados / total * 100:.0f}%)")
    print(f"  consultas que se quedan sin negativos: {sin_negativos}")
    print(f"  consultas utilizables: {len(limpios)} de {len(registros)}")
    return limpios


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--epocas", type=float, default=1.0)
    p.add_argument("--lote", type=int, default=8)
    p.add_argument("--acumular", type=int, default=4)
    p.add_argument("--salida", default=str(SALIDA))
    args = p.parse_args()

    import torch

    if not torch.cuda.is_available():
        print("FALLO: sin GPU. Este script es para la 5080.")
        return 1
    print("GPU:", torch.cuda.get_device_name(0))

    registros = [json.loads(x) for x in PARES.read_text(encoding="utf-8").splitlines() if x.strip()]
    print(f"{len(registros)} consultas con sus negativos")

    print("\nLimpiando negativos falsos con el cross-encoder...", flush=True)
    registros = limpiar_negativos_falsos(registros)

    from datasets import Dataset

    filas = {"anchor": [], "positive": [], "negative": []}
    for d in registros:
        for negativo in d["negativos"]:
            filas["anchor"].append("query: " + d["consulta"])
            filas["positive"].append("passage: " + d["positivo"])
            filas["negative"].append("passage: " + negativo)
    datos = Dataset.from_dict(filas)
    print(f"\n{len(datos)} tripletas de entrenamiento")

    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )
    from sentence_transformers.losses import MultipleNegativesRankingLoss

    modelo = SentenceTransformer(BASE)
    modelo.max_seq_length = 512

    entrenamiento = SentenceTransformerTrainingArguments(
        output_dir=str(Path(args.salida).parent / "_entrenamiento"),
        num_train_epochs=args.epocas,
        per_device_train_batch_size=args.lote,
        gradient_accumulation_steps=args.acumular,
        learning_rate=2e-5,
        warmup_ratio=0.1,
        fp16=True,
        logging_steps=20,
        save_strategy="no",
        report_to=[],
    )
    SentenceTransformerTrainer(
        model=modelo,
        args=entrenamiento,
        train_dataset=datos,
        loss=MultipleNegativesRankingLoss(modelo),
    ).train()

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    modelo.save_pretrained(args.salida)
    print(f"\nmodelo afinado en {args.salida}")

    # Prueba de cordura: si no distingue lo pertinente de lo impertinente, algo
    # salio mal y no vale la pena gastar 6 horas de reindexado en averiguarlo.
    import numpy as np

    v = modelo.encode(
        [
            "query: me echaron del trabajo estando incapacitado",
            "passage: estabilidad laboral reforzada del trabajador en condicion de debilidad manifiesta",
            "passage: regimen aduanero de importacion temporal",
        ]
    )

    def sim(a, b):
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))

    pertinente, impertinente = sim(v[0], v[1]), sim(v[0], v[2])
    print(f"prueba de cordura -> pertinente {pertinente:.3f} | impertinente {impertinente:.3f}")
    if pertinente <= impertinente:
        print("FALLO: el modelo afinado no distingue. No usarlo.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
