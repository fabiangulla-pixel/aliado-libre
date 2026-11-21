"""Preguntas coloquiales sinteticas (doc2query) como tercera lista de la fusion RRF.

Una consulta coloquial ("me cortaron la luz") y el articulo que la responde
("suspension del servicio publico domiciliario") no comparten palabras ni se
parecen en el espacio vectorial. Por adelantado, un LLM local escribio para los
articulos de las normas de uso cotidiano preguntas como las haria una persona
de a pie (finetune/doc2query/). Aqui se busca la consulta entre ESAS preguntas
(pregunta contra pregunta, que si se parecen) y cada acierto vota por su
fragmento. En tiempo de consulta no interviene ningun LLM: es un producto
punto contra una matriz precalculada.

Apagado por defecto: `ALIADO_PESO_PREGUNTAS` (0 = apagado) hasta medirlo.

    .venv/Scripts/python.exe -m index.preguntas construir
    -> index/preguntas_sinteticas.npz
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "index" / "preguntas_sinteticas.npz"
ORIGEN = RAIZ / "finetune" / "doc2query" / "preguntas.jsonl"
PESO_PREGUNTAS = float(os.environ.get("ALIADO_PESO_PREGUNTAS", "0") or 0)
# Cuantas preguntas vecinas se miran: varias preguntas votan por el mismo fragmento.
VECINAS = 400
# Similitud coseno minima para que una pregunta sintetica aporte (0 = sin
# filtro). La lista solo contiene las normas cubiertas: sin filtro, con peso
# alto empuja esas normas aunque la consulta sea de otro tema (21-nov-2026,
# peso 2: el equivalente@5 cae de 51.6% a 33.7%).
UMBRAL = float(os.environ.get("ALIADO_UMBRAL_PREGUNTAS", "0") or 0)

_matriz: np.ndarray | None = None
_fragmentos: np.ndarray | None = None
_candado = threading.Lock()


def _cargar() -> bool:
    global _matriz, _fragmentos
    if _matriz is not None:
        return True
    with _candado:
        if _matriz is None:
            if not ARCHIVO.exists():
                return False
            datos = np.load(ARCHIVO, allow_pickle=False)
            _matriz = datos["emb"].astype(np.float32)
            _fragmentos = datos["fragmentos"]
    return True


def lista_preguntas(embedding_consulta, n: int) -> list[str]:
    """Ids de fragmento ordenados por su pregunta sintetica mas parecida."""
    if not PESO_PREGUNTAS or not _cargar():
        return []
    q = np.asarray(embedding_consulta, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1.0)
    sims = _matriz @ q
    vecinas = min(VECINAS, len(sims))
    mejores = np.argpartition(-sims, vecinas - 1)[:vecinas]
    mejores = mejores[np.argsort(-sims[mejores])]
    salida, vistos = [], set()
    for i in mejores:
        if sims[i] < UMBRAL:
            break  # ordenadas de mayor a menor: las demas tampoco pasan
        frag = str(_fragmentos[i])
        if frag not in vistos:
            vistos.add(frag)
            salida.append(frag)
            if len(salida) >= n:
                break
    return salida


def construir() -> None:
    from sentence_transformers import SentenceTransformer

    from index.buscar import MODELO_EMBEDDINGS, PREFIJO_CONSULTA

    textos, frags = [], []
    for linea in ORIGEN.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        d = json.loads(linea)
        for p in d["preguntas"]:
            textos.append(p)
            frags.append(d["id"])
    modelo = SentenceTransformer(MODELO_EMBEDDINGS)
    # Mismo prefijo que la consulta del usuario: se compara pregunta con pregunta.
    emb = modelo.encode(
        [PREFIJO_CONSULTA + t for t in textos],
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    np.savez(ARCHIVO, emb=emb.astype(np.float16), fragmentos=np.array(frags))
    print(f"{len(textos)} preguntas de {len(set(frags))} fragmentos -> {ARCHIVO}")


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["construir"]:
        construir()
