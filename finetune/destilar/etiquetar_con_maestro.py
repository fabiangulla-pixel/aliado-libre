#!/usr/bin/env python3
"""Sonnet como MAESTRO: ordena los candidatos de miles de consultas, una sola vez.

El producto final no llama a ninguna IA de nube (decisión del 6-oct-2026): Sonnet
solo enseña. Aquí elige los 10 documentos que mejor responden cada consulta de
entrenamiento, entre los que trae la búsqueda local de hoy; con eso se afina un
reordenador local (`entrenar_reordenador.py`) que hace lo mismo sin conexión.

Por qué el pool sale de la búsqueda de HOY y sin reformular: el alumno, en
producción, solo verá lo que trae la búsqueda local. Si el maestro eligiera entre
candidatos que el alumno nunca recibirá, el alumno aprendería otra tarea.

Consultas (ninguna de los bancos de prueba, por texto ni por documento):
- consultas_vulnerables.json (Haiku, en la voz de adulto mayor y baja alfabetización);
- consultas_reales_google.json (lo que la gente de verdad escribe);
- las consultas de pares_embedding.jsonl (8 perfiles).

Dos pasos, con checkpoint:
  --pools      arma los candidatos (local, gratis, GPU);
  --ejecutar   manda el lote a Sonnet (Batch API, mitad de precio) y recoge.

Uso:
    .venv/Scripts/python.exe finetune/destilar/etiquetar_con_maestro.py --pools
    .venv/Scripts/python.exe finetune/destilar/etiquetar_con_maestro.py            # estima
    .venv/Scripts/python.exe finetune/destilar/etiquetar_con_maestro.py --ejecutar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "finetune" / "eval"))

import lab_recuperacion as lab  # noqa: E402
import reordenar_amplio as ra  # noqa: E402

MAESTRO = "claude-sonnet-5"
DIR = Path(__file__).resolve().parent
POOLS = DIR / "pools.json"
ETIQUETAS = DIR / "etiquetas_maestro.json"
LOTE = RAIZ / "_run" / "maestro_lote.json"
N_MOTOR = 120
DOCUMENTOS = 60
EXTRACTO = 400


def _normal(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


def consultas() -> list[dict]:
    ev = RAIZ / "finetune" / "eval"
    prueba = []
    for nombre in ("banco_piloto_100.json", "banco_prueba_200.json"):
        prueba += json.loads((ev / nombre).read_text(encoding="utf-8"))
    textos_prueba = {_normal(c["consulta"]) for c in prueba}
    docs_prueba = {c.get("documento_id") for c in prueba if c.get("documento_id")}

    salida: list[dict] = []
    vul = DIR / "consultas_vulnerables.json"
    if vul.exists():
        salida += json.loads(vul.read_text(encoding="utf-8"))
    for c in json.loads((ev / "consultas_reales_google.json").read_text(encoding="utf-8")):
        salida.append({"consulta": c["consulta"], "perfil": "real_google", "fuente": "google"})
    with open(RAIZ / "finetune" / "data" / "pares_embedding.jsonl", encoding="utf-8") as f:
        for linea in f:
            p = json.loads(linea)
            salida.append(
                {"consulta": p["consulta"], "perfil": p.get("perfil", ""), "fuente": "pares_embedding"}
            )

    vistas: set[str] = set()
    limpias = []
    for c in salida:
        clave = _normal(c["consulta"])
        if not clave or clave in vistas or clave in textos_prueba or c.get("documento_id") in docs_prueba:
            continue
        vistas.add(clave)
        c["qid"] = "q" + hashlib.sha1(clave.encode()).hexdigest()[:12]
        limpias.append(c)
    return limpias


def armar_pools() -> None:
    from index.buscar import PREFIJO_CONSULTA, IndiceBusqueda, _consulta_fts, _tokenizar

    pools: dict = json.loads(POOLS.read_text(encoding="utf-8")) if POOLS.exists() else {}
    cs = [c for c in consultas() if c["qid"] not in pools]
    print(f"{len(cs)} consultas sin pool ({len(pools)} ya hechas)")
    ix = IndiceBusqueda()
    for i, c in enumerate(cs, 1):
        emb = ix._modelo.encode([PREFIJO_CONSULTA + c["consulta"]]).tolist()
        vec = ix._coleccion.query(query_embeddings=emb, n_results=N_MOTOR)["ids"][0]
        fts: list[str] = []
        match = _consulta_fts(_tokenizar(c["consulta"]))
        if ix._fts is not None and match:
            fts = [
                f[0]
                for f in ix._fts.execute(
                    "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT ?",
                    (match, N_MOTOR),
                ).fetchall()
            ]
        orden = lab.fusionar(vec, fts, 0.8)
        pools[c["qid"]] = {**c, "pool": ra.un_fragmento_por_documento(orden, 150)}
        if i % 200 == 0:
            POOLS.write_text(json.dumps(pools, ensure_ascii=False), encoding="utf-8")
            print(f"  {i}/{len(cs)}", flush=True)
    POOLS.write_text(json.dumps(pools, ensure_ascii=False), encoding="utf-8")
    print(f"Pools: {len(pools)} en {POOLS}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pools", action="store_true")
    ap.add_argument("--ejecutar", action="store_true")
    a = ap.parse_args()
    if a.pools:
        armar_pools()
        return 0

    pools = json.loads(POOLS.read_text(encoding="utf-8"))
    etiquetas: dict = json.loads(ETIQUETAS.read_text(encoding="utf-8")) if ETIQUETAS.exists() else {}
    pendientes = [q for q in pools if q not in etiquetas and pools[q]["pool"]]
    print(f"{len(pendientes)} consultas por etiquetar con {MAESTRO} (pool de {DOCUMENTOS} documentos)")
    # costo real medido el 3-oct: 0,0247 USD por consulta con 60 documentos; Batch = mitad
    print(f"Estimado con Batch: {len(pendientes) * 0.0247 / 2:.2f} USD")
    if not a.ejecutar:
        return 0

    import anthropic
    import chromadb

    from finetune.clave_api import leer_clave
    from index import costos
    from index.buscar import COLECCION, DIR_INDICE

    cliente = anthropic.Anthropic(api_key=leer_clave(obligatoria=True))
    if not LOTE.exists() and pendientes:
        col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
        pedidos = []
        for n, qid in enumerate(pendientes, 1):
            pool = pools[qid]["pool"][:DOCUMENTOS]
            datos = col.get(ids=pool, include=["documents", "metadatas"])
            textos = dict(zip(datos["ids"], datos["documents"], strict=True))
            metas = dict(zip(datos["ids"], datos["metadatas"], strict=True))
            lineas = [
                f"[{i}] {(metas.get(f) or {}).get('titulo_documento') or lab.documento_de(f)}\n"
                + re.sub(r"\s+", " ", textos.get(f) or "")[:EXTRACTO]
                for i, f in enumerate(pool, 1)
            ]
            prompt = (
                f"Pregunta: {pools[qid]['consulta']}\n\nDocumentos:\n\n"
                + "\n\n".join(lineas)
                + f"\n\nLos {ra.ELEGIDOS} mejores:"
            )
            pedidos.append(
                {
                    "custom_id": qid,
                    "params": {
                        "model": MAESTRO,
                        "max_tokens": 8000,
                        "system": ra.SISTEMA_ORDENAR,
                        "messages": [{"role": "user", "content": prompt}],
                        **ra._config(MAESTRO),
                    },
                }
            )
            if n % 500 == 0:
                print(f"  armados {n}/{len(pendientes)}", flush=True)
        lote = cliente.messages.batches.create(requests=pedidos)
        LOTE.write_text(json.dumps({"id": lote.id}), encoding="utf-8")
        print(f"Lote enviado: {lote.id} ({len(pedidos)} consultas)", flush=True)

    lote_id = json.loads(LOTE.read_text(encoding="utf-8"))["id"]
    while True:
        estado = cliente.messages.batches.retrieve(lote_id)
        if estado.processing_status == "ended":
            break
        print(
            f"  lote: {estado.request_counts.succeeded} listas, {estado.request_counts.processing} en curso",
            flush=True,
        )
        time.sleep(120)

    usd, fallos = 0.0, 0
    for r in cliente.messages.batches.results(lote_id):
        if r.result.type != "succeeded" or r.result.message.stop_reason == "refusal":
            fallos += 1
            continue
        msg = r.result.message
        usd += costos.liquidar(msg.usage, MAESTRO).usd / 2
        texto = "".join(b.text for b in msg.content if b.type == "text")
        pool = pools[r.custom_id]["pool"][:DOCUMENTOS]
        elegidos = [pool[i - 1] for i in ra.interpretar(texto, len(pool))]
        if elegidos:
            etiquetas[r.custom_id] = {"elegidos": elegidos, "pool_visto": pool}
    ETIQUETAS.write_text(json.dumps(etiquetas, ensure_ascii=False), encoding="utf-8")
    LOTE.replace(LOTE.with_suffix(".hecho.json"))
    print(f"Etiquetadas: {len(etiquetas)} | fallos {fallos} | costo real {usd:.2f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
