#!/usr/bin/env python3
"""Consulta reescrita por un LLM + reordenamiento amplio por el mismo LLM.

Diagnóstico del 3-oct-2026 sobre el piloto (95 anclas): el documento correcto
está entre los 120 primeros de algún motor el 70% de las veces, pero llega al
top-5 de producción el 27%. El reordenamiento con LLM del 30-sep solo veía 30
documentos (techo 23/44) y la reescritura del 12-sep usaba el modelo local
pequeño. Aquí se prueban las dos cosas juntas y con modelos fuertes:

1. El LLM escribe 3 reformulaciones en el vocabulario de la norma. Cada una se
   busca con los dos motores; sus listas se suman a las de la consulta original.
2. Se fusiona todo por RRF, se toma un candidato por documento hasta DOCUMENTOS
   y el LLM elige y ordena los 10 más útiles.

Se informa por separado lo que aporta cada paso: base, base + reescritura (sin
reordenar, gratis una vez hecha la reescritura) y reescritura + reordenamiento.
Los pasos del LLM se guardan por consulta en un archivo de avance: si el proceso
muere, al relanzarlo no se vuelve a pagar lo ya hecho.

Uso:
    .venv/Scripts/python.exe finetune/eval/reordenar_amplio.py --modelo claude-opus-5-5           # estima
    .venv/Scripts/python.exe finetune/eval/reordenar_amplio.py --modelo claude-opus-5-5 --ejecutar
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lab_recuperacion as lab  # noqa: E402

N_MOTOR = 120  # candidatos por motor y por consulta (como el cache)
DOCUMENTOS = 60  # documentos distintos que ve el LLM
EXTRACTO = 400  # caracteres del fragmento representativo
ELEGIDOS = 10
REFORMULACIONES = 3
DIR_SALIDA = RAIZ / "finetune" / "eval" / "reordenar_amplio"

SISTEMA_REESCRIBIR = f"""Eres un abogado colombiano. Una persona sin formación jurídica \
describe un problema con sus palabras. Escribe {REFORMULACIONES} reformulaciones de su \
pregunta como las buscaría un abogado en la legislación y la jurisprudencia \
colombianas: con el vocabulario de la norma, la figura jurídica y la rama del \
derecho que aplica. Cada una en una línea, sin numerar, sin explicar. No inventes \
números de ley, de artículo ni de sentencia: un número inventado lleva la búsqueda \
al documento equivocado."""

SISTEMA_ORDENAR = f"""Eres un abogado colombiano que ayuda a una persona sin formación \
jurídica a encontrar la norma que responde su pregunta. Recibes la pregunta, escrita \
como la escribe la persona, y una lista numerada de documentos candidatos (título y un \
extracto). Elige los {ELEGIDOS} documentos que MEJOR responden la pregunta, del más útil \
al menos útil. Piensa en qué problema jurídico describe realmente la persona aunque no \
use el vocabulario jurídico. Prefiere la norma que regula el asunto sobre la que solo \
lo menciona. Responde SOLO con los números separados por comas."""


# Configuración por modelo. Opus 5.5 no deja apagar el razonamiento: se baja el
# esfuerzo. Haiku no tiene esfuerzo.
def _config(modelo: str) -> dict:
    if modelo.startswith("claude-haiku"):
        return {}
    return {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}


def llamar(cliente, modelo: str, sistema: str, texto: str):
    msg = cliente.messages.create(
        model=modelo,
        max_tokens=8000,
        system=sistema,
        messages=[{"role": "user", "content": texto}],
        **_config(modelo),
    )
    salida = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    return salida, msg.usage, msg.stop_reason


def candidatos_fusionados(listas: list[list[str]]) -> list[str]:
    """RRF sobre varias listas; la léxica pesa 0,8 como en producción."""
    puntaje: dict[str, float] = {}
    for i, lista in enumerate(listas):
        peso = 1.0 if i % 2 == 0 else 0.8  # pares (vectorial, léxica)
        for rango, frag in enumerate(lista):
            puntaje[frag] = puntaje.get(frag, 0) + peso / (lab.K_RRF + rango)
    return [f for f, _ in sorted(puntaje.items(), key=lambda x: -x[1])]


def un_fragmento_por_documento(orden: list[str], n: int) -> list[str]:
    vistos, salida = set(), []
    for frag in orden:
        doc = lab.documento_de(frag)
        if doc not in vistos:
            vistos.add(doc)
            salida.append(frag)
            if len(salida) == n:
                break
    return salida


def interpretar(texto: str, n: int) -> list[int]:
    elegidos: list[int] = []
    for m in re.findall(r"\d+", texto or ""):
        i = int(m)
        if 1 <= i <= n and i not in elegidos:
            elegidos.append(i)
    return elegidos[:ELEGIDOS]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--documentos", type=int, default=DOCUMENTOS, help="documentos que ve el LLM")
    ap.add_argument("--subconjunto", choices=["dev", "test", "todo"], default="dev")
    ap.add_argument("--ejecutar", action="store_true", help="gasta de verdad; sin esto solo estima")
    a = ap.parse_args()

    from index import costos

    cache = pickle.loads(lab.CACHE.read_bytes())
    reparto = lab.particion()
    casos = [
        c
        for c in lab.casos_anclados()
        if c["id"] in cache and (a.subconjunto == "todo" or reparto.get(c["documento_id"]) == a.subconjunto)
    ]
    entrada, salida = costos.PRECIOS[a.modelo]
    # Por consulta: reescritura ~600 tokens de entrada; ordenar ~DOCUMENTOS*130.
    # Salida con razonamiento a esfuerzo bajo: ~1.500 tokens en total.
    estimado = len(casos) * ((600 + a.documentos * 130) * entrada + 1500 * salida) / 1e6
    print(f"{len(casos)} consultas ({a.subconjunto}) | {a.modelo} | estimado {estimado:.2f} USD")
    if not a.ejecutar:
        print("No se llamó a ninguna API. Añade --ejecutar para medir.")
        return 0

    import anthropic
    import chromadb

    from finetune.clave_api import leer_clave
    from index.buscar import (
        COLECCION,
        DIR_INDICE,
        PREFIJO_CONSULTA,
        IndiceBusqueda,
        _consulta_fts,
        _tokenizar,
    )

    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    sufijo = "" if a.documentos == DOCUMENTOS else f"_{a.documentos}docs"
    avance_ruta = DIR_SALIDA / f"avance_{a.modelo}{sufijo}.json"
    avance: dict = json.loads(avance_ruta.read_text(encoding="utf-8")) if avance_ruta.exists() else {}
    # Las reformulaciones no dependen del tamano del pool: se reusan las ya
    # pagadas para que la comparacion aisle el efecto de ver mas documentos.
    previo = DIR_SALIDA / f"avance_{a.modelo}.json"
    if sufijo and previo.exists():
        for k, v in json.loads(previo.read_text(encoding="utf-8")).items():
            avance.setdefault(k, {"reformulaciones": v["reformulaciones"], "usd_reescribir": 0.0})

    cliente = anthropic.Anthropic(api_key=leer_clave(obligatoria=True))
    ix = IndiceBusqueda()
    coleccion = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)

    def buscar_dos_motores(texto: str) -> list[list[str]]:
        emb = ix._modelo.encode([PREFIJO_CONSULTA + texto]).tolist()
        vec = ix._coleccion.query(query_embeddings=emb, n_results=N_MOTOR)["ids"][0]
        fts: list[str] = []
        match = _consulta_fts(_tokenizar(texto))
        if ix._fts is not None and match:
            fts = [
                f[0]
                for f in ix._fts.execute(
                    "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT ?",
                    (match, N_MOTOR),
                ).fetchall()
            ]
        return [vec, fts]

    usd = 0.0
    filas = []
    for n, c in enumerate(casos, 1):
        reg = avance.get(c["id"], {})
        if "reformulaciones" not in reg:
            texto, uso, stop = llamar(cliente, a.modelo, SISTEMA_REESCRIBIR, c["consulta"])
            reg["reformulaciones"] = [x.strip(" -•") for x in texto.splitlines() if x.strip()][
                :REFORMULACIONES
            ]
            reg["usd_reescribir"] = costos.liquidar(uso, a.modelo).usd
            reg["stop_reescribir"] = stop

        d = cache[c["id"]]
        listas = [d["vectorial"], d["fts"]]
        for r in reg["reformulaciones"]:
            listas += buscar_dos_motores(r)
        orden_reescrito = candidatos_fusionados(listas)
        pool = un_fragmento_por_documento(orden_reescrito, a.documentos)

        if "salida_ordenar" not in reg:
            datos = coleccion.get(ids=pool, include=["documents", "metadatas"])
            textos = dict(zip(datos["ids"], datos["documents"], strict=True))
            metas = dict(zip(datos["ids"], datos["metadatas"], strict=True))
            lineas = []
            for i, f in enumerate(pool, 1):
                titulo = (metas.get(f) or {}).get("titulo_documento") or lab.documento_de(f)
                extracto = re.sub(r"\s+", " ", textos.get(f) or "")[:EXTRACTO]
                lineas.append(f"[{i}] {titulo}\n{extracto}")
            prompt = (
                f"Pregunta: {c['consulta']}\n\nDocumentos:\n\n"
                + "\n\n".join(lineas)
                + f"\n\nLos {ELEGIDOS} mejores:"
            )
            texto, uso, stop = llamar(cliente, a.modelo, SISTEMA_ORDENAR, prompt)
            reg["salida_ordenar"] = texto
            reg["pool"] = pool
            reg["usd_ordenar"] = costos.liquidar(uso, a.modelo).usd
            reg["stop_ordenar"] = stop

        avance[c["id"]] = reg
        avance_ruta.write_text(json.dumps(avance, ensure_ascii=False, indent=1), encoding="utf-8")
        usd += reg["usd_reescribir"] + reg["usd_ordenar"]

        pool = reg["pool"]
        elegidos = [pool[i - 1] for i in interpretar(reg["salida_ordenar"], len(pool))]
        orden_llm = elegidos + [f for f in orden_reescrito if f not in elegidos]
        filas.append(
            {
                "id": c["id"],
                "perfil": c["perfil"],
                "base": lab.rango_documento(lab.fusionar(d["vectorial"], d["fts"], 0.8), c["documento_id"]),
                "reescrito": lab.rango_documento(orden_reescrito, c["documento_id"]),
                "en_pool": lab.rango_documento(pool, c["documento_id"]) is not None,
                "llm": lab.rango_documento(orden_llm, c["documento_id"]),
            }
        )
        if n % 10 == 0:
            print(f"  {n}/{len(casos)}  gasto acumulado {usd:.2f} USD", flush=True)

    (DIR_SALIDA / f"resultado_{a.modelo}{sufijo}_{a.subconjunto}.json").write_text(
        json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n{a.modelo} — {a.subconjunto} (n={len(filas)})")
    print(
        f"techo: el documento correcto entra en los {a.documentos} que ve el LLM en "
        f"{sum(f['en_pool'] for f in filas)}/{len(filas)}"
    )
    for clave in ("base", "reescrito", "llm"):
        m = lab.metricas_rango([f[clave] for f in filas])
        print(
            f"  {clave:10} "
            + "  ".join(
                f"{k} {v:.3f}" if k.startswith("mrr") else f"{k} {v * 100:.1f}%" for k, v in m.items()
            )
        )
    gana = sum(1 for f in filas if (f["llm"] or 999) <= 5 < (f["base"] or 999))
    pierde = sum(1 for f in filas if (f["base"] or 999) <= 5 < (f["llm"] or 999))
    print(f"top-5 frente a producción: gana {gana}, pierde {pierde}")
    print(f"Costo real: {usd:.3f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
