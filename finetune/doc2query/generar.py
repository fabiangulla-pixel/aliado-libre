"""Paso 2 de doc2query: preguntas coloquiales por fragmento, con un LLM LOCAL.

La nube no interviene (regla del proyecto: las IA de nube ensenan y miden; lo
que corre es local). Usa Ollama (http://localhost:11434) con gemma4:26b.
(LM Studio no sirve desde aqui: su servicio no arranca sin sesion interactiva.)

Reanudable: una linea JSON por fragmento con fsync; al relanzar salta los hechos.

    .venv/Scripts/python.exe finetune/doc2query/generar.py
    -> finetune/doc2query/preguntas.jsonl
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
CARPETA = RAIZ / "finetune" / "doc2query"
ENTRADA = CARPETA / "fragmentos.jsonl"
SALIDA = CARPETA / "preguntas.jsonl"
URL = os.environ.get("D2Q_URL", "http://localhost:11434/api/chat")
MODELO = os.environ.get("D2Q_MODELO", "gemma4:26b")
MAX_TEXTO = 2500  # caracteres del fragmento que ve el modelo

INSTRUCCION = """Eres una persona colombiana común (no abogada). Te muestro un fragmento de una norma colombiana sobre: {tema}.

Escribe 6 preguntas DISTINTAS que haría una persona de a pie cuya situación real se resuelve con ESTE fragmento. Reglas:
- Habla como la gente: en primera persona, con tu caso concreto ("me echaron", "el arrendador no me devuelve el depósito", "me cortaron el agua").
- NO uses términos jurídicos del texto (nada de "empleador", "terminación unilateral", "suspensión del servicio", "obligación alimentaria"); di lo mismo con palabras de la calle.
- NO cites números de ley ni de artículo.
- Varía el estilo: una corta tipo mensaje de WhatsApp sin tildes, una de una persona mayor que da rodeos, una con algo de contexto irrelevante, una muy directa.
- Si el fragmento es solo un encabezado, una lista de derogatorias o no le sirve a una persona común, responde exactamente: []

Responde SOLO con una lista JSON de cadenas.

FRAGMENTO ({titulo}):
{texto}"""  # noqa: E501


def hechos() -> set[str]:
    if not SALIDA.exists():
        return set()
    ids = set()
    datos = SALIDA.read_bytes()
    if datos and not datos.endswith(b"\n"):  # linea a medias de un corte
        corte = datos.rfind(b"\n") + 1
        SALIDA.write_bytes(datos[:corte])
    for linea in SALIDA.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            ids.add(json.loads(linea)["id"])
    return ids


def preguntar(frag: dict) -> list[str]:
    # API nativa de Ollama: `think: false` apaga el razonamiento (gemma4 lo trae
    # encendido y se comia los tokens: con max 600 devolvia la respuesta vacia).
    cuerpo = {
        "model": MODELO,
        "messages": [
            {
                "role": "user",
                "content": INSTRUCCION.format(
                    tema=frag["tema"], titulo=frag["titulo"][:120], texto=frag["texto"][:MAX_TEXTO]
                ),
            }
        ],
        "think": False,
        "stream": False,
        "options": {"temperature": 0.8, "num_predict": 600, "num_ctx": 3072},
    }
    req = urllib.request.Request(
        URL, data=json.dumps(cuerpo).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        texto = json.loads(r.read())["message"]["content"]
    m = re.search(r"\[.*\]", texto, re.S)
    if not m:
        return []
    try:
        lista = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [p.strip() for p in lista if isinstance(p, str) and 10 <= len(p.strip()) <= 400][:8]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ya = hechos()
    frags = [json.loads(linea) for linea in ENTRADA.read_text(encoding="utf-8").splitlines() if linea.strip()]
    pendientes = [f for f in frags if f["id"] not in ya]
    # Normas cortas primero: los codigos enormes (Tributario, Comercio, CGP)
    # al final, para que un corte deje cubiertas las leyes enteras.
    tam = {}
    for f in frags:
        tam[f["documento_id"]] = tam.get(f["documento_id"], 0) + 1
    pendientes.sort(key=lambda f: tam[f["documento_id"]])
    print(f"{len(frags)} fragmentos; {len(ya)} hechos; {len(pendientes)} pendientes", flush=True)
    t0, n = time.time(), 0
    with SALIDA.open("a", encoding="utf-8") as out:
        for frag in pendientes:
            espera = 10
            while True:
                try:
                    preguntas = preguntar(frag)
                    break
                except OSError as e:  # servidor caido o reiniciando: esperar, no perder el fragmento
                    print(f"  servidor: {e}; reintento en {espera} s", flush=True)
                    time.sleep(espera)
                    espera = min(espera * 2, 300)
            out.write(
                json.dumps(
                    {"id": frag["id"], "documento_id": frag["documento_id"], "preguntas": preguntas},
                    ensure_ascii=False,
                )
                + "\n"
            )
            out.flush()
            os.fsync(out.fileno())
            n += 1
            if n % 25 == 0:
                ritmo = n / (time.time() - t0)
                print(
                    f"{time.strftime('%H:%M:%S')} {n}/{len(pendientes)} | {ritmo * 3600:.0f}/h | "
                    f"quedan ~{(len(pendientes) - n) / ritmo / 60:.0f} min",
                    flush=True,
                )
    print("FIN", flush=True)


if __name__ == "__main__":
    main()
