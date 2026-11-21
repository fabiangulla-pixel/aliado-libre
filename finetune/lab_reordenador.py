"""Laboratorio de reordenamiento sobre pools FIJOS (finetune/eval/reordenador_cpu/pools_*.json).

Cada modelo puntua una sola vez cada par (consulta, candidato); despues se
prueban combinaciones (modelo solo, mezcla con el orden de la fusion RRF,
conjuntos de modelos) en segundos y sin GPU. Una sola variable a la vez: los
candidatos son siempre los mismos.

    python finetune/lab_reordenador.py puntuar bge piloto
    python finetune/lab_reordenador.py puntuar qwen4b piloto
    python finetune/lab_reordenador.py evaluar piloto

Se elige con piloto (dev). banco_prueba_200 se mira una vez (D-06).
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.stdout.reconfigure(encoding="utf-8")

POOLS = RAIZ / "finetune" / "eval" / "reordenador_cpu"
CARPETA = RAIZ / "finetune" / "eval" / "lab"
BANCOS = {"piloto": "banco_piloto_100.json", "prueba": "banco_prueba_200.json"}

INSTRUCCION_QWEN = (
    "Given a legal question written in everyday Colombian Spanish by a non-lawyer, judge whether the "
    "document contains the legal provision, doctrine or ruling that answers it"
)


def cargar_pools(banco: str) -> list[dict]:
    pools = json.loads((POOLS / f"pools_{banco}.json").read_text(encoding="utf-8"))
    for c in pools:
        if isinstance(c["pool"], str):
            c["pool"] = ast.literal_eval(c["pool"])
    return pools


def pasaje(r: dict) -> str:
    from index.reordenar import _pasaje

    return _pasaje(r)


def _puntuar_cross(nombre_hf: str, pools: list[dict]) -> list[list[float]]:
    import torch
    from sentence_transformers import CrossEncoder

    ce = CrossEncoder(nombre_hf, max_length=512, model_kwargs={"torch_dtype": torch.float16})
    return [
        [float(s) for s in ce.predict([(c["consulta"], pasaje(r)) for r in c["pool"]], batch_size=32)]
        for c in pools
    ]


def _puntuar_qwen(nombre_hf: str, pools: list[dict]) -> list[list[float]]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(nombre_hf, padding_side="left")
    modelo = AutoModelForCausalLM.from_pretrained(nombre_hf, torch_dtype=torch.float16).cuda().eval()
    si, no = tok.convert_tokens_to_ids("yes"), tok.convert_tokens_to_ids("no")
    prefijo = (
        "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and "
        'the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
    )
    sufijo = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    salida = []
    for c in pools:
        textos = [
            f"{prefijo}<Instruct>: {INSTRUCCION_QWEN}\n<Query>: {c['consulta']}\n<Document>: {pasaje(r)}{sufijo}"  # noqa: E501
            for r in c["pool"]
        ]
        puntajes = []
        for i in range(0, len(textos), 12):
            lote = tok(
                textos[i : i + 12], padding=True, truncation=True, max_length=1024, return_tensors="pt"
            )
            with torch.no_grad():
                logits = modelo(**{k: v.cuda() for k, v in lote.items()}).logits[:, -1, :]
            par = torch.stack([logits[:, no], logits[:, si]], dim=1).float().log_softmax(dim=1)
            puntajes += par[:, 1].exp().tolist()
        salida.append(puntajes)
    return salida


MODELOS = {
    "bge": ("BAAI/bge-reranker-v2-m3", _puntuar_cross),
    "mini": ("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", _puntuar_cross),
    "qwen4b": ("Qwen/Qwen3-Reranker-4B", _puntuar_qwen),
    "qwen06": ("Qwen/Qwen3-Reranker-0.6B", _puntuar_qwen),
}


def puntuar(modelo: str, banco: str) -> None:
    pools = cargar_pools(banco)
    nombre_hf, fn = MODELOS[modelo]
    t0 = time.time()
    puntajes = fn(nombre_hf, pools)
    s = (time.time() - t0) / len(pools)
    CARPETA.mkdir(parents=True, exist_ok=True)
    (CARPETA / f"{banco}_{modelo}.json").write_text(
        json.dumps({"s_por_consulta": s, "puntajes": puntajes}), encoding="utf-8"
    )
    print(f"{modelo} {banco}: {len(pools)} consultas, {s:.2f} s/consulta (GPU, incluye carga)")


def _rangos(valores: list[float]) -> np.ndarray:
    """0 = mejor; para mezclar escalas distintas se usa el rango, no el puntaje."""
    orden = np.argsort(-np.asarray(valores), kind="stable")
    r = np.empty(len(valores))
    r[orden] = np.arange(len(valores))
    return r


def evaluar(banco: str) -> None:
    from finetune.eval.acierto import posicion
    from index.buscar import limitar_sentencias, un_fragmento_por_documento

    pools = cargar_pools(banco)
    casos = {
        c["consulta"]: c
        for c in json.loads(
            (RAIZ / "finetune" / "eval" / BANCOS[re.match(r"[a-z]+", banco).group(0)]).read_text(
                encoding="utf-8"
            )
        )
    }
    disponibles = {
        m: json.loads((CARPETA / f"{banco}_{m}.json").read_text(encoding="utf-8"))["puntajes"]
        for m in MODELOS
        if (CARPETA / f"{banco}_{m}.json").exists()
    }
    variantes: dict[str, callable] = {"rrf": lambda i, n: -np.arange(n, dtype=float)}
    for m in disponibles:
        variantes[m] = lambda i, n, m=m: np.asarray(disponibles[m][i])
        for a in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
            variantes[f"{m}+rrf{a}"] = lambda i, n, m=m, a=a: (
                -((1 - a) * _rangos(disponibles[m][i]) + a * np.arange(n))
            )
    nombres = list(disponibles)
    for x in range(len(nombres)):
        for y in range(x + 1, len(nombres)):
            a, b = nombres[x], nombres[y]
            variantes[f"{a}+{b}"] = lambda i, n, a=a, b=b: (
                -(_rangos(disponibles[a][i]) + _rangos(disponibles[b][i]))
            )
    print(f"{banco}: n={len(pools)} | #1 equivalente / @5 exacto / @5 equivalente / MRR@10 equivalente")
    filas = []
    for nombre, fn in variantes.items():
        ex = eq = rr = uno = 0.0
        for i, c in enumerate(pools):
            caso = casos[c["consulta"]]
            puntos = fn(i, len(c["pool"]))
            # MaxP: el documento queda en la posicion de su mejor fragmento
            orden = un_fragmento_por_documento([c["pool"][j] for j in np.argsort(-puntos, kind="stable")])
            top5 = limitar_sentencias(orden, 5)  # igual que produccion (k=5)
            ex += posicion(top5, caso) is not None
            eq += posicion(top5, caso, equivalente=True) is not None
            uno += posicion(top5[:1], caso, equivalente=True) is not None
            pq = posicion(limitar_sentencias(orden, 10), caso, equivalente=True)
            rr += 1 / (pq + 1) if pq is not None else 0
        n = len(pools)
        filas.append((uno / n, eq / n, nombre, ex / n, rr / n))
    for uno, eq, nombre, ex, rr in sorted(filas, reverse=True):
        print(f"  {nombre:18} {uno * 100:5.1f}%  {ex * 100:5.1f}%  {eq * 100:5.1f}%  {rr:.3f}")


if __name__ == "__main__":
    accion = sys.argv[1]
    if accion == "puntuar":
        puntuar(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "piloto")
    elif accion == "evaluar":
        evaluar(sys.argv[2] if len(sys.argv) > 2 else "piloto")
