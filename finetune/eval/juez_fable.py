#!/usr/bin/env python3
"""Segundo juez de pertinencia, independiente: Claude Fable 5.1 sobre los mismos pares.

Por qué: `juzgar_pertinencia.py` dio éxito@5 de 96,8% a la búsqueda asistida por
Sonnet, pero el juez también era Sonnet: juzgaba sus propias elecciones. Aquí
otro modelo (de otra familia, más capaz) juzga exactamente los mismos pares, con
el mismo criterio y sin ver las notas de Sonnet. Se reporta:

- acuerdo y kappa de Cohen entre los dos jueces (3 clases y binario "responde");
- éxito@5 de cada sistema con las notas de Fable.

⚠️ Sigue siendo juicio de IA, no verdad de referencia humana. Un acuerdo alto
dice que la métrica no depende del juez; no dice que una persona coincidiría.

Batch API (50% del precio). El lote se guarda en `_run/juez_fable_lote.txt` y el
script se puede relanzar: si el lote ya existe, solo recoge resultados.

Uso:
    .venv/Scripts/python.exe finetune/eval/juez_fable.py            # estima
    .venv/Scripts/python.exe finetune/eval/juez_fable.py --ejecutar  # envía o recoge
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import juzgar_pertinencia as jp  # noqa: E402
import lab_recuperacion as lab  # noqa: E402

JUEZ = "claude-fable-5-1"
SALIDA = RAIZ / "finetune" / "eval" / "juicios_pertinencia_fable.json"
LOTE = RAIZ / "_run" / "juez_fable_lote.txt"


def kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def comparar(sonnet: dict, fable: dict) -> None:
    pares = [(cid, f) for cid, js in sonnet.items() for f in js if f in fable.get(cid, {})]
    s = [sonnet[c][f] for c, f in pares]
    fb = [fable[c][f] for c, f in pares]
    print(f"\nPares juzgados por los dos: {len(pares)}")
    iguales = sum(x == y for x, y in zip(s, fb, strict=True))
    print(f"  acuerdo exacto (0/1/2): {iguales / len(pares) * 100:.1f}%")
    print(f"  kappa 3 clases: {kappa(s, fb):.3f}")
    sb, fbb = [int(x == 2) for x in s], [int(x == 2) for x in fb]
    print(f"  kappa binario (responde=2 vs no): {kappa(sb, fbb):.3f}")
    print(f"  Sonnet da 2 en {sum(sb)}; Fable da 2 en {sum(fbb)}")
    print(f"  Sonnet=2 y Fable<2: {sum(1 for x, y in zip(sb, fbb, strict=True) if x and not y)}")
    print(f"  Fable=2 y Sonnet<2: {sum(1 for x, y in zip(sb, fbb, strict=True) if y and not x)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ejecutar", action="store_true")
    a = ap.parse_args()

    sonnet = json.loads(jp.JUICIOS.read_text(encoding="utf-8"))
    casos = lab.casos_anclados()
    consulta_de = {c["id"]: c["consulta"] for c in casos}
    fable: dict = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}

    # Todo lo que algún sistema pone en su top-10 (incluido el índice actual) y
    # Fable no ha juzgado todavía; los pares de Sonnet entran siempre.
    pares = jp.pares_a_juzgar(jp.sistemas())
    for cid, js in sonnet.items():
        pares.setdefault(cid, [])
        pares[cid] += [f for f in js if f not in pares[cid]]
    pendientes = {
        cid: [f for f in fs if f not in fable.get(cid, {})] for cid, fs in pares.items() if cid in consulta_de
    }
    pendientes = {cid: fs for cid, fs in pendientes.items() if fs}
    n = sum(len(v) for v in pendientes.values())
    print(f"{n} pares en {len(pendientes)} consultas por juzgar con {JUEZ}")
    if not a.ejecutar:
        ent = n * 380 + len(pendientes) * 600
        print(
            f"Estimado con Batch: {(ent * 10 + len(pendientes) * 1500 * 50) / 2e6:.2f} USD. Añade --ejecutar."
        )
        if fable:
            comparar(sonnet, fable)
        return 0

    import anthropic
    import chromadb

    from finetune.clave_api import leer_clave
    from index import costos
    from index.buscar import COLECCION, DIR_INDICE

    cliente = anthropic.Anthropic(api_key=leer_clave(obligatoria=True))

    if pendientes and not LOTE.exists():
        col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
        pedidos = []
        orden: dict[str, list[str]] = {}
        rng = random.Random(51)
        for cid, frags in pendientes.items():
            frags = list(frags)
            rng.shuffle(frags)  # otro orden que el de Sonnet: que la posición no pese
            datos = col.get(ids=frags, include=["documents", "metadatas"])
            texto = dict(zip(datos["ids"], datos["documents"], strict=True))
            meta = dict(zip(datos["ids"], datos["metadatas"], strict=True))
            frags = [f for f in frags if f in texto]
            orden[cid] = frags
            lineas = [
                f"[{i}] {(meta.get(f) or {}).get('titulo_documento', '')}\n"
                + re.sub(r"\s+", " ", texto[f] or "")[: jp.EXTRACTO]
                for i, f in enumerate(frags, 1)
            ]
            prompt = f"Pregunta: {consulta_de[cid]}\n\nFragmentos:\n\n" + "\n\n".join(lineas)
            pedidos.append(
                {
                    "custom_id": cid,
                    "params": {
                        "model": JUEZ,
                        "max_tokens": 16000,
                        "system": jp.SISTEMA,
                        "output_config": {"effort": "medium"},
                        "messages": [{"role": "user", "content": prompt}],
                    },
                }
            )
        lote = cliente.messages.batches.create(requests=pedidos)
        LOTE.parent.mkdir(exist_ok=True)
        LOTE.write_text(json.dumps({"id": lote.id, "orden": orden}, ensure_ascii=False), encoding="utf-8")
        print(f"Lote enviado: {lote.id} ({len(pedidos)} consultas)")

    if LOTE.exists():
        info = json.loads(LOTE.read_text(encoding="utf-8"))
        while True:
            estado = cliente.messages.batches.retrieve(info["id"])
            if estado.processing_status == "ended":
                break
            print(f"  lote {estado.processing_status}: {estado.request_counts}", flush=True)
            time.sleep(60)
        usd = 0.0
        fallos = 0
        for r in cliente.messages.batches.results(info["id"]):
            if r.result.type != "succeeded":
                fallos += 1
                continue
            msg = r.result.message
            usd += costos.liquidar(msg.usage, JUEZ).usd / 2  # Batch: mitad de precio
            if msg.stop_reason == "refusal":
                fallos += 1
                continue
            salida = "".join(b.text for b in msg.content if b.type == "text")
            m = re.search(r"\{.*\}", salida, re.S)
            notas = json.loads(m.group(0)) if m else {}
            frags = info["orden"][r.custom_id]
            fable.setdefault(r.custom_id, {}).update(
                {f: notas[str(i)] for i, f in enumerate(frags, 1) if notas.get(str(i)) in (0, 1, 2)}
            )
        SALIDA.write_text(json.dumps(fable, ensure_ascii=False, indent=1), encoding="utf-8")
        LOTE.replace(LOTE.with_suffix(".hecho.txt"))
        print(f"Costo real: {usd:.2f} USD | consultas fallidas: {fallos}")

    comparar(sonnet, fable)
    print("\néxito@5 con las notas de FABLE:")
    jp.informe(jp.sistemas(), fable, casos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
