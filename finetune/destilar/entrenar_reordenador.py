#!/usr/bin/env python3
"""Afina el reordenador local (bge-reranker-v2-m3) para que ordene como el maestro.

Datos: `etiquetas_maestro.json` (los 10 documentos que Sonnet eligió entre los 60
de la búsqueda local, por consulta). Por cada consulta:
  - elegidos 1-3 del maestro  -> etiqueta 1,0
  - elegidos 4-10             -> 0,7 (sirven, pero hay mejores)
  - NEG_POR_CONSULTA no elegidos del pool -> 0,0 (negativos difíciles: la búsqueda
    los trajo, el maestro los descartó)
Pérdida: entropía cruzada binaria con etiquetas graduadas.

El 10% de las consultas (por hash, estable) queda fuera para validar: cuántos
de los 5 primeros del maestro pone el alumno en su top-5 sobre el mismo pool.

Lo que decide si el modelo entra NO es esto, es `evaluar_reordenador.py` sobre los
bancos de prueba, que nunca se usan para entrenar.

Uso:
    .venv/Scripts/python.exe finetune/destilar/entrenar_reordenador.py
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

DIR = Path(__file__).resolve().parent
SALIDA = RAIZ / "modelos" / "reranker_destilado"
BASE = "BAAI/bge-reranker-v2-m3"
NEG_POR_CONSULTA = 10
MAX_CARACTERES = 2000
SEMILLA = 20261006


def es_validacion(qid: str) -> bool:
    return int(hashlib.sha1(qid.encode()).hexdigest(), 16) % 10 == 0


def textos_de(ids: list[str]) -> dict[str, str]:
    import chromadb

    from index.buscar import COLECCION, DIR_INDICE

    col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    salida: dict[str, str] = {}
    for i in range(0, len(ids), 2000):
        datos = col.get(ids=ids[i : i + 2000], include=["documents", "metadatas"])
        for fid, doc, meta in zip(datos["ids"], datos["documents"], datos["metadatas"], strict=True):
            titulo = (meta or {}).get("titulo_documento") or ""
            salida[fid] = f"{titulo}\n{doc or ''}"[:MAX_CARACTERES]
    return salida


def armar(etiquetas: dict, pools: dict) -> tuple[list[dict], list[str]]:
    rng = random.Random(SEMILLA)
    filas: list[dict] = []
    validacion: list[str] = []
    for qid, et in etiquetas.items():
        if es_validacion(qid):
            validacion.append(qid)
            continue
        consulta = pools[qid]["consulta"]
        elegidos = et["elegidos"]
        for rango, f in enumerate(elegidos):
            filas.append({"q": consulta, "f": f, "y": 1.0 if rango < 3 else 0.7})
        resto = [f for f in et["pool_visto"] if f not in elegidos]
        for f in rng.sample(resto, min(NEG_POR_CONSULTA, len(resto))):
            filas.append({"q": consulta, "f": f, "y": 0.0})
    rng.shuffle(filas)
    return filas, validacion


def acuerdo_con_maestro(modelo, etiquetas: dict, pools: dict, qids: list[str], textos: dict) -> float:
    aciertos, total = 0, 0
    for qid in qids:
        et = etiquetas[qid]
        pool = [f for f in et["pool_visto"] if f in textos]
        puntajes = modelo.predict([(pools[qid]["consulta"], textos[f]) for f in pool], batch_size=64)
        top = {f for _, f in sorted(zip(puntajes, pool, strict=True), key=lambda x: -x[0])[:5]}
        maestro = set(et["elegidos"][:5])
        aciertos += len(top & maestro)
        total += len(maestro)
    return aciertos / max(total, 1)


def main() -> int:
    import torch
    from datasets import Dataset
    from sentence_transformers.cross_encoder import (
        CrossEncoder,
        CrossEncoderTrainer,
        CrossEncoderTrainingArguments,
    )
    from sentence_transformers.cross_encoder.losses import BinaryCrossEntropyLoss

    etiquetas = json.loads((DIR / "etiquetas_maestro.json").read_text(encoding="utf-8"))
    pools = json.loads((DIR / "pools.json").read_text(encoding="utf-8"))
    filas, validacion = armar(etiquetas, pools)
    ids = sorted({r["f"] for r in filas} | {f for q in validacion for f in etiquetas[q]["pool_visto"]})
    print(f"{len(etiquetas)} consultas etiquetadas | {len(filas)} pares | {len(validacion)} validación")
    textos = textos_de(ids)
    filas = [r for r in filas if r["f"] in textos]
    ds = Dataset.from_dict(
        {
            "query": [r["q"] for r in filas],
            "passage": [textos[r["f"]] for r in filas],
            "label": [r["y"] for r in filas],
        }
    )

    modelo = CrossEncoder(BASE, num_labels=1, max_length=512)
    antes = acuerdo_con_maestro(modelo, etiquetas, pools, validacion, textos)
    print(f"Acuerdo con el maestro ANTES (top-5 sobre el mismo pool, validación): {antes:.3f}", flush=True)

    args = CrossEncoderTrainingArguments(
        output_dir=str(RAIZ / "_run" / "entreno_reranker"),
        num_train_epochs=1,
        per_device_train_batch_size=16,
        gradient_accumulation_steps=2,
        learning_rate=2e-5,
        warmup_ratio=0.1,
        bf16=torch.cuda.is_available(),
        logging_steps=50,
        save_strategy="no",
        report_to=[],
        seed=SEMILLA,
    )
    CrossEncoderTrainer(
        model=modelo, args=args, train_dataset=ds, loss=BinaryCrossEntropyLoss(modelo)
    ).train()

    despues = acuerdo_con_maestro(modelo, etiquetas, pools, validacion, textos)
    print(f"Acuerdo con el maestro DESPUÉS: {despues:.3f}")
    SALIDA.mkdir(parents=True, exist_ok=True)
    modelo.save_pretrained(str(SALIDA))
    (SALIDA / "entrenamiento.json").write_text(
        json.dumps(
            {
                "base": BASE,
                "consultas": len(etiquetas),
                "pares": len(filas),
                "validacion": len(validacion),
                "acuerdo_antes": antes,
                "acuerdo_despues": despues,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"Modelo en {SALIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
