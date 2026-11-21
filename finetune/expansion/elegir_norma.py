"""Enrutador por ELECCION: el LLM elige entre las normas que trajo la busqueda.

El enrutador libre (norma_llm.py) nombra de memoria la ley GENERAL (Ley 100,
Estatuto Tributario, Codigo de Comercio) cuando la respuesta es el decreto
especifico que la reglamenta: 19 de los 53 fallos en dev del 21-nov. Aqui se le
muestran solo las NORMAS distintas entre los primeros candidatos de la fusion
(titulo + inicio del fragmento) y elige una o ninguna: puede preferir el
decreto especifico y no puede nombrar una que no este.

    python finetune/expansion/elegir_norma.py piloto150 30
    -> finetune/eval/expansion/piloto150_elegir30.json   {consulta: indice o null}
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
sys.path.insert(0, str(RAIZ))
URL = os.environ.get("D2Q_URL", "http://localhost:11434/api/chat")
MODELO = os.environ.get("ELEGIR_MODELO", "gemma4:26b")

PROMPT = """Una persona en Colombia pregunta:
"{consulta}"

Estas son normas colombianas candidatas:

{candidatas}

¿Cual de ellas regula MAS DIRECTA y especificamente su situacion? Si una norma reglamenta en detalle el tema, preferirla sobre la ley general. Responde SOLO con el numero, o 0 si ninguna aplica."""  # noqa: E501


def candidatas(documentos: list[dict], n: int) -> list[dict]:
    """Normas distintas entre los primeros n documentos, en su orden."""
    from index.normas import norma_de_resultado

    vistas, salida = set(), []
    for r in documentos[:n]:
        nr = norma_de_resultado(r)
        if nr and nr not in vistas:
            vistas.add(nr)
            salida.append(r)
    return salida


def elegir(consulta: str, cands: list[dict]) -> int | None:
    if not cands:
        return None
    bloques = "\n".join(
        f"[{i + 1}] {(r.get('titulo_documento') or '')[:140]} — {(r.get('texto') or '')[:220]}".replace(
            "\n", " "
        )
        for i, r in enumerate(cands)
    )
    cuerpo = {
        "model": MODELO,
        "messages": [{"role": "user", "content": PROMPT.format(consulta=consulta, candidatas=bloques)}],
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 6, "num_ctx": 8192},
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
    return i if 0 <= i < len(cands) else None


def main(banco: str, n: int) -> None:
    from finetune.lab_reordenador import cargar_pools
    from index.buscar import un_fragmento_por_documento

    sys.stdout.reconfigure(encoding="utf-8")
    salida = RAIZ / "finetune" / "eval" / "expansion" / f"{banco}_elegir{n}.json"
    hechos = json.loads(salida.read_text(encoding="utf-8")) if salida.exists() else {}
    t0 = time.time()
    for p in cargar_pools(banco):
        if p["consulta"] in hechos:
            continue
        cands = candidatas(un_fragmento_por_documento(p["pool"]), n)
        i = elegir(p["consulta"], cands)
        hechos[p["consulta"]] = None if i is None else cands[i]["documento_id"]
        salida.write_text(json.dumps(hechos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"FIN {salida.name} {(time.time() - t0) / max(len(hechos), 1):.1f} s/consulta", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 30)
