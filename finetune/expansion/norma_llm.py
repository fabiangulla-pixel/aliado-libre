"""Que norma regula el caso, segun un LLM LOCAL. Enrutador para el puesto 1.

Medido el 21-nov-2026 en dev (piloto, 95): gemma4:26b nombra la norma correcta
en el 60% de los casos cuya respuesta es una norma. Si esa norma ya esta entre
los candidatos de la fusion, subirla al puesto 1 lleva el acierto en #1 de
31.6% a 44.2%; cuando coincide con el #1 de la fusion, acierta el 87%.

    python finetune/expansion/norma_llm.py piloto gemma4:26b
    python finetune/expansion/norma_llm.py piloto qwen3:4b cpu
    -> finetune/eval/expansion/piloto_norma_<modelo>.json  {consulta: respuesta}

Reanudable. Ollama local; nada sale a la nube.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
URL = os.environ.get("D2Q_URL", "http://localhost:11434/api/chat")
BANCOS = {"piloto": "banco_piloto_100.json", "prueba": "banco_prueba_200.json"}

PROMPT = """Una persona en Colombia pregunta:
"{consulta}"

¿Que ley, decreto o codigo colombiano vigente regula directamente su situacion? Responde SOLO con su nombre y numero, por ejemplo "Ley 1480 de 2011 (Estatuto del Consumidor)" o "Codigo Sustantivo del Trabajo". Si no lo sabes con seguridad, responde "no se"."""  # noqa: E501


def preguntar(consulta: str, modelo: str, cpu: bool = False) -> str:
    opciones = {"temperature": 0, "num_predict": 40, "num_ctx": 1024}
    if cpu:
        opciones["num_gpu"] = 0
    cuerpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": PROMPT.format(consulta=consulta)}],
        "think": False,
        "stream": False,
        "options": opciones,
    }
    req = urllib.request.Request(
        URL, data=json.dumps(cuerpo).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["message"]["content"].strip()


def main(banco: str, modelo: str, cpu: bool) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    casos = [
        c
        for c in json.loads((RAIZ / "finetune" / "eval" / BANCOS[banco]).read_text(encoding="utf-8"))
        if c.get("documento_id")
    ]
    carpeta = RAIZ / "finetune" / "eval" / "expansion"
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = (
        carpeta / f"{banco}_norma_{re.sub(r'[^a-z0-9.]+', '_', modelo.lower())}{'_cpu' if cpu else ''}.json"
    )
    hechos = json.loads(salida.read_text(encoding="utf-8")) if salida.exists() else {}
    tiempos = []
    for c in casos:
        if c["consulta"] in hechos:
            continue
        t = time.time()
        hechos[c["consulta"]] = preguntar(c["consulta"], modelo, cpu)
        tiempos.append(time.time() - t)
        salida.write_text(json.dumps(hechos, ensure_ascii=False, indent=1), encoding="utf-8")
    if tiempos:
        # la primera incluye cargar el modelo
        print(
            f"{modelo} {'cpu' if cpu else 'gpu'}: mediana {sorted(tiempos)[len(tiempos) // 2]:.1f} s/consulta"
        )
    print(f"FIN {salida.name}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], len(sys.argv) > 3 and sys.argv[3] == "cpu")
