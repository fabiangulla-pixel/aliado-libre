#!/usr/bin/env python3
"""Consultas en la voz de los perfiles que hoy dan 0%: adulto mayor y baja alfabetización.

Para destilar el reordenador hacen falta consultas de entrenamiento escritas como
escribe la gente que el sistema no atiende: en el piloto, `adulto_mayor_informal`
y `baja_alfabetizacion` siguen en 0-2 de 14 incluso con Sonnet. Si el maestro solo
ve consultas de Google y de abogados, el alumno aprende a servirles a ellos.

Haiku 4.5 escribe las consultas (escribir preguntas sí lo hace bien; elegir
documentos no, 27,3% medido el 3-oct). Parte de fragmentos REALES de fuentes que
responden problemas cotidianos, y puede negarse si el fragmento no es algo que
una persona preguntaría. Se excluyen los documentos de los dos bancos de prueba
(piloto_100 y prueba_200): nada de lo que se mide puede entrar al entrenamiento.

Batch API (mitad de precio). Uso:
    .venv/Scripts/python.exe finetune/destilar/generar_consultas_vulnerables.py            # estima
    .venv/Scripts/python.exe finetune/destilar/generar_consultas_vulnerables.py --ejecutar
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "finetune"))

from generar_banco_coloquial import PERFILES  # noqa: E402

from ingest.chunking import fragmentar  # noqa: E402
from ingest.schema import Documento  # noqa: E402

MODELO = "claude-haiku-4-5"
DIR = Path(__file__).resolve().parent
SALIDA = DIR / "consultas_vulnerables.json"
LOTE = RAIZ / "_run" / "consultas_vulnerables_lote.json"  # uno a la vez
SEMILLA = 20261006
PERFILES_OBJETIVO = ("adulto_mayor_informal", "baja_alfabetizacion")
# Fuentes donde están los problemas cotidianos, y cuántos fragmentos de cada una.
CUOTAS = {
    "superservicios": 110,
    "supersalud": 70,
    "corte_constitucional_texto": 110,  # tutelas: salud, trabajo, pensión
    "corte_constitucional": 60,
    "gestor_normativo": 70,
    "sic": 30,
    "superfinanciera": 20,
}

SISTEMA = """Ayudas a construir datos de entrenamiento para un buscador legal colombiano \
pensado para personas sin formación jurídica. Te doy un fragmento real de una norma, \
sentencia o concepto. Si el fragmento resuelve un problema que una persona común podría \
tener (trabajo, salud, servicios públicos, pensión, familia, vivienda, deudas, consumo), \
escribe una consulta por cada perfil indicado, como esa persona la escribiría, sin usar \
el vocabulario del fragmento ni nombrar normas. Si el fragmento es puramente técnico, \
procesal o interno del Estado, responde {"no_sirve": true}. Responde SOLO con JSON."""


def _ids_de_prueba() -> set[str]:
    ids: set[str] = set()
    for nombre in ("banco_piloto_100.json", "banco_prueba_200.json"):
        for c in json.loads((RAIZ / "finetune" / "eval" / nombre).read_text(encoding="utf-8")):
            if c.get("documento_id"):
                ids.add(c["documento_id"])
    return ids


def muestrear(ronda: int = 0, excluir_frags: set[str] | None = None) -> list[dict]:
    rng = random.Random(SEMILLA + ronda)
    excluir_frags = excluir_frags or set()
    excluir = _ids_de_prueba()
    muestra = []
    for archivo, n in CUOTAS.items():
        docs = [
            Documento(**d)
            for d in json.loads((RAIZ / "data" / "raw" / f"{archivo}.json").read_text(encoding="utf-8"))
        ]
        docs = [d for d in docs if d.id not in excluir]
        if archivo.startswith("corte"):
            docs = [d for d in docs if d.identificador.startswith("T-")]  # tutelas: lo cotidiano
        rng.shuffle(docs)
        tomados = 0
        for d in docs:
            frags = [f for f in fragmentar(d) if len(f.texto) > 400]
            if not frags:
                continue
            frags = [f for f in frags if f.id not in excluir_frags]
            if not frags:
                continue
            f = rng.choice(frags)
            muestra.append(
                {"documento_id": d.id, "fragmento_id": f.id, "titulo": d.titulo, "texto": f.texto[:1500]}
            )
            tomados += 1
            if tomados >= n:
                break
    return muestra


def prompt_de(m: dict) -> str:
    perfiles = "\n".join(f'- "{p}": {PERFILES[p]}' for p in PERFILES_OBJETIVO)
    return (
        f"Perfiles:\n{perfiles}\n\nFragmento ({m['titulo']}):\n{m['texto']}\n\n"
        'Formato: {"adulto_mayor_informal": "...", "baja_alfabetizacion": "..."} o {"no_sirve": true}'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ejecutar", action="store_true")
    ap.add_argument("--ronda", type=int, default=0, help="otra muestra; se suma a lo ya generado")
    a = ap.parse_args()

    previas: list[dict] = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else []
    muestra = muestrear(a.ronda, {c["fragmento_id"] for c in previas})
    print(f"{len(muestra)} fragmentos muestreados")
    entrada = sum(len(prompt_de(m)) for m in muestra) / 3.5 + len(muestra) * 200
    print(f"Estimado con Batch ({MODELO}): {(entrada * 1 + len(muestra) * 200 * 5) / 2e6:.2f} USD")
    if not a.ejecutar:
        return 0

    import anthropic

    from finetune.clave_api import leer_clave
    from index import costos

    cliente = anthropic.Anthropic(api_key=leer_clave(obligatoria=True))
    if not LOTE.exists():
        lote = cliente.messages.batches.create(
            requests=[
                {
                    "custom_id": f"m{i}",
                    "params": {
                        "model": MODELO,
                        "max_tokens": 600,
                        "system": SISTEMA,
                        "messages": [{"role": "user", "content": prompt_de(m)}],
                    },
                }
                for i, m in enumerate(muestra)
            ]
        )
        LOTE.write_text(json.dumps({"id": lote.id}), encoding="utf-8")
        print(f"Lote enviado: {lote.id}")
    lote_id = json.loads(LOTE.read_text(encoding="utf-8"))["id"]
    while cliente.messages.batches.retrieve(lote_id).processing_status != "ended":
        time.sleep(30)

    consultas, usd, no_sirve = list(previas), 0.0, 0
    for r in cliente.messages.batches.results(lote_id):
        if r.result.type != "succeeded":
            continue
        msg = r.result.message
        usd += costos.liquidar(msg.usage, MODELO).usd / 2
        texto = "".join(b.text for b in msg.content if b.type == "text")
        m = re.search(r"\{.*\}", texto, re.S)
        try:
            datos = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            continue
        if datos.get("no_sirve"):
            no_sirve += 1
            continue
        origen = muestra[int(r.custom_id[1:])]
        for perfil in PERFILES_OBJETIVO:
            q = (datos.get(perfil) or "").strip()
            if len(q) > 10:
                consultas.append(
                    {
                        "consulta": q,
                        "perfil": perfil,
                        "documento_id": origen["documento_id"],
                        "fragmento_id": origen["fragmento_id"],
                        "fuente": "sintetica_haiku",
                    }
                )
    SALIDA.write_text(json.dumps(consultas, ensure_ascii=False, indent=1), encoding="utf-8")
    LOTE.replace(LOTE.with_suffix(".hecho.json"))
    print(f"{len(consultas)} consultas ({no_sirve} no servían) | {usd:.2f} USD -> {SALIDA.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
