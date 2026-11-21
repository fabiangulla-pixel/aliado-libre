"""Query2Doc / HyDE con un LLM LOCAL: la pregunta coloquial + un pasaje juridico hipotetico.

El LLM escribe lo que diria la norma que resuelve el caso, en el lenguaje de
las normas; se busca con pregunta + pasaje. Ataca la brecha de vocabulario
("me echaron" vs "terminacion del contrato sin justa causa") desde el lado de
la consulta, como doc2query la ataca desde el lado del indice.

    python finetune/expansion/hyde.py piloto
    -> finetune/eval/expansion/piloto_q2d.json   {consulta: consulta + pasaje}

Se mide con:
    set MEDIR_EXPANSION=finetune/eval/expansion/piloto_q2d.json
    python finetune/medir_dev.py correr q2d

Reanudable. Ollama local (gemma4:26b); nada sale a la nube.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
URL = os.environ.get("D2Q_URL", "http://localhost:11434/api/chat")
MODELO = os.environ.get("HYDE_MODELO", "gemma4:26b")
BANCOS = {"piloto": "banco_piloto_100.json", "prueba": "banco_prueba_200.json"}

PROMPT = """Una persona en Colombia pregunta:
"{consulta}"

Escribe, en 3 a 5 frases, el texto juridico que resolveria su caso, con el vocabulario de las normas colombianas (como si fuera el articulo de la ley o un concepto oficial). Nombra la ley o el codigo que lo regula si lo sabes con seguridad; si no, no inventes numeros. No le hables a la persona ni des consejos: solo el texto juridico."""  # noqa: E501


def pasaje(consulta: str) -> str:
    cuerpo = {
        "model": MODELO,
        "messages": [{"role": "user", "content": PROMPT.format(consulta=consulta)}],
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 300, "num_ctx": 2048},
    }
    req = urllib.request.Request(
        URL, data=json.dumps(cuerpo).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["message"]["content"].strip()


def main(banco: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    casos = [
        c
        for c in json.loads((RAIZ / "finetune" / "eval" / BANCOS[banco]).read_text(encoding="utf-8"))
        if c.get("documento_id")
    ]
    carpeta = RAIZ / "finetune" / "eval" / "expansion"
    carpeta.mkdir(parents=True, exist_ok=True)
    crudo_f = carpeta / f"{banco}_pasajes.json"
    crudo = json.loads(crudo_f.read_text(encoding="utf-8")) if crudo_f.exists() else {}
    t0 = time.time()
    for i, c in enumerate(casos):
        if c["consulta"] in crudo:
            continue
        crudo[c["consulta"]] = pasaje(c["consulta"])
        crudo_f.write_text(json.dumps(crudo, ensure_ascii=False, indent=1), encoding="utf-8")
        if i % 10 == 0:
            print(f"{i}/{len(casos)} {(time.time() - t0) / (i + 1):.1f} s/consulta", flush=True)
    (carpeta / f"{banco}_q2d.json").write_text(
        json.dumps({k: f"{k}\n{v}" for k, v in crudo.items()}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (carpeta / f"{banco}_hyde.json").write_text(
        json.dumps(crudo, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("FIN", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "piloto")
