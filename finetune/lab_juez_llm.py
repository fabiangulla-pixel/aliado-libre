"""Juez final con un LLM LOCAL: de los K mejores documentos, cual va primero.

Sobre los pools fijos del laboratorio y los puntajes ya guardados de un
reordenador (finetune/eval/lab/{banco}_{modelo}.json). El LLM ve la pregunta y
los K candidatos (titulo + fragmento) y responde el numero del que la resuelve;
ese pasa al primer lugar y el resto conserva su orden. La meta medida es la
norma correcta en el puesto 1.

    python finetune/lab_juez_llm.py piloto150 qwen4b 10

Ollama local (gemma4:26b). Las IA de nube no corren aqui.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ.get("D2Q_URL", "http://localhost:11434/api/chat")
MODELO = os.environ.get("JUEZ_MODELO", "gemma4:26b")
CHARS = 700  # por candidato

PROMPT = """Una persona en Colombia pregunta:
"{consulta}"

Estos son documentos juridicos candidatos. Elige el UNO que mejor resuelve su situacion: la norma, sentencia o concepto que un abogado le mandaria a leer primero. Preferir la norma que regula directamente el caso sobre una que solo lo menciona.

{candidatos}

Responde SOLO con el numero del candidato elegido."""  # noqa: E501


def elegir(consulta: str, candidatos: list[dict]) -> int | None:
    bloques = "\n\n".join(
        f"[{i + 1}] {(r.get('titulo_documento') or '')[:150]}\n{(r.get('texto') or '')[:CHARS]}"
        for i, r in enumerate(candidatos)
    )
    cuerpo = {
        "model": MODELO,
        "messages": [{"role": "user", "content": PROMPT.format(consulta=consulta, candidatos=bloques)}],
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 8, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        URL, data=json.dumps(cuerpo).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        texto = json.loads(r.read())["message"]["content"]
    m = re.search(r"\d+", texto)
    if not m:
        return None
    i = int(m.group(0)) - 1
    return i if 0 <= i < len(candidatos) else None


def main(banco: str, modelo: str, k: int) -> None:
    from finetune.eval.acierto import posicion
    from finetune.lab_reordenador import BANCOS, CARPETA, cargar_pools
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
    if modelo == "rrf":
        puntajes = [list(-np.arange(len(c["pool"]), dtype=float)) for c in pools]
    else:
        puntajes = json.loads((CARPETA / f"{banco}_{modelo}.json").read_text(encoding="utf-8"))["puntajes"]
    salida = CARPETA / f"{banco}_{modelo}_juez{k}.json"
    hechos = json.loads(salida.read_text(encoding="utf-8")) if salida.exists() else {}
    antes1 = despues1 = antes5 = despues5 = 0
    t0 = time.time()
    for i, c in enumerate(pools):
        caso = casos[c["consulta"]]
        orden = un_fragmento_por_documento(
            [c["pool"][j] for j in np.argsort(-np.asarray(puntajes[i]), kind="stable")]
        )
        top = limitar_sentencias(orden, k)
        if c["consulta"] not in hechos:
            hechos[c["consulta"]] = elegir(c["consulta"], top)
            salida.write_text(json.dumps(hechos, ensure_ascii=False), encoding="utf-8")
        e = hechos[c["consulta"]]
        nuevo = ([top[e]] + [r for j, r in enumerate(top) if j != e]) if e is not None else top
        antes1 += posicion(top[:1], caso, equivalente=True) is not None
        despues1 += posicion(nuevo[:1], caso, equivalente=True) is not None
        antes5 += posicion(top[:5], caso, equivalente=True) is not None
        despues5 += posicion(nuevo[:5], caso, equivalente=True) is not None
    n = len(pools)
    print(
        f"{banco} {modelo} juez@{k}: #1 {antes1 / n * 100:.1f}% -> {despues1 / n * 100:.1f}% | "
        f"@5 {antes5 / n * 100:.1f}% -> {despues5 / n * 100:.1f}% | {(time.time() - t0) / n:.1f} s/consulta"
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10)
