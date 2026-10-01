#!/usr/bin/env python3
"""¿Puede un LLM reordenar los candidatos que la búsqueda ya encuentra?

Diagnóstico del 12/29-sep: el documento correcto está entre los 120 candidatos el
69% de las veces y entre los 5 primeros solo el 27%. Ninguna reordenación
determinista lo mueve (pesos RRF, agregación por documento, ventanas: medido el
30-sep), y el cross-encoder bge-reranker EMPEORABA con consultas reales: no
entiende que «me cortaron la luz» pide la Ley 142 de servicios públicos.

Aquí un LLM recibe la consulta y los 30 documentos candidatos (título + extracto)
y devuelve los 5 más útiles. Se mide sobre la caché de candidatos del banco de
ensayos, con la misma métrica que la línea base (recall@k y MRR por documento).

Uso:
    .venv/Scripts/python.exe finetune/eval/reordenar_llm.py --subconjunto dev           # estima, no gasta
    .venv/Scripts/python.exe finetune/eval/reordenar_llm.py --subconjunto dev --ejecutar
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

VENTANA = 40  # candidatos por motor antes de fusionar (como producción, algo más ancho)
DOCUMENTOS = 30  # documentos distintos que ve el LLM
EXTRACTO = 350  # caracteres por documento
SALIDA = RAIZ / "finetune" / "eval" / "resultado_reordenar_llm.json"

SISTEMA = """Eres un abogado colombiano que ayuda a una persona sin formación jurídica a \
encontrar la norma que responde su pregunta. Recibes la pregunta, escrita como la \
escribe la persona, y una lista numerada de documentos candidatos (título y un \
extracto). Elige los 5 documentos que MEJOR responden la pregunta, del más útil al \
menos útil. Piensa en qué rama del derecho y qué norma trata realmente el problema \
que describe la persona, aunque no use el vocabulario jurídico. Prefiere la norma \
que regula el asunto sobre la que solo lo menciona. Responde SOLO con los números \
separados por comas, por ejemplo: 7, 2, 19, 4, 11"""


def candidatos_por_documento(d: dict) -> list[str]:
    """Fragmentos de los primeros DOCUMENTOS documentos distintos, en orden RRF."""
    orden = lab.fusionar(d["vectorial"][:VENTANA], d["fts"][:VENTANA], 0.8)
    vistos, salida = set(), []
    for frag in orden:
        doc = lab.documento_de(frag)
        if doc not in vistos:
            vistos.add(doc)
            salida.append(frag)
        if len(salida) == DOCUMENTOS:
            break
    return salida


def armar_prompt(consulta: str, frags: list[str], textos: dict, metas: dict) -> str:
    lineas = []
    for i, f in enumerate(frags, 1):
        titulo = (metas.get(f) or {}).get("titulo_documento") or lab.documento_de(f)
        extracto = re.sub(r"\s+", " ", textos.get(f, ""))[:EXTRACTO]
        lineas.append(f"[{i}] {titulo}\n{extracto}")
    return f"Pregunta: {consulta}\n\nDocumentos:\n\n" + "\n\n".join(lineas) + "\n\nLos 5 mejores:"


def interpretar(texto: str, n: int) -> list[int]:
    elegidos = []
    for m in re.findall(r"\d+", texto or ""):
        i = int(m)
        if 1 <= i <= n and i not in elegidos:
            elegidos.append(i)
    return elegidos[:5]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subconjunto", choices=["dev", "test", "todo"], default="dev")
    ap.add_argument("--ejecutar", action="store_true", help="gasta de verdad; sin esto solo estima")
    a = ap.parse_args()

    import chromadb

    from index import costos
    from index.buscar import COLECCION, DIR_INDICE
    from index.proveedores import MODELOS_POR_DEFECTO, generar

    cache = pickle.loads(lab.CACHE.read_bytes())
    reparto = lab.particion()
    casos = [
        c
        for c in lab.casos_anclados()
        if c["id"] in cache and (a.subconjunto == "todo" or reparto.get(c["documento_id"]) == a.subconjunto)
    ]
    coleccion = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    modelo = MODELOS_POR_DEFECTO["claude"]

    prompts = []
    for c in casos:
        frags = candidatos_por_documento(cache[c["id"]])
        datos = coleccion.get(ids=frags, include=["documents", "metadatas"])
        textos = dict(zip(datos["ids"], datos["documents"], strict=True))
        metas = dict(zip(datos["ids"], datos["metadatas"], strict=True))
        prompts.append((c, frags, armar_prompt(c["consulta"], frags, textos, metas)))

    estimado = sum(costos.estimar(p, modelo).usd for _, _, p in prompts)
    print(f"{len(prompts)} consultas ({a.subconjunto}) | {modelo} | estimado {estimado:.2f} USD")
    if not a.ejecutar:
        print("No se llamó a ninguna API. Añade --ejecutar para medir.")
        return 0

    from finetune.clave_api import leer_clave

    clave = leer_clave(obligatoria=True)
    base_rangos, llm_rangos, filas, usd = [], [], [], 0.0
    for c, frags, prompt in prompts:
        base_rangos.append(
            lab.rango_documento(
                lab.fusionar(cache[c["id"]]["vectorial"], cache[c["id"]]["fts"], 0.8), c["documento_id"]
            )
        )
        r = generar(prompt, SISTEMA, "claude", clave=clave, modelo=modelo)
        usd += costos.liquidar(r.usage, r.modelo).usd
        elegidos = [frags[i - 1] for i in interpretar(r.texto, len(frags))]
        resto = [f for f in frags if f not in elegidos]
        orden = elegidos + resto
        llm_rangos.append(lab.rango_documento(orden, c["documento_id"]))
        filas.append(
            {
                "id": c["id"],
                "perfil": c["perfil"],
                "salida_llm": r.texto,
                "rango_base": base_rangos[-1],
                "rango_llm": llm_rangos[-1],
            }
        )

    SALIDA.with_name(f"resultado_reordenar_llm_{a.subconjunto}.json").write_text(
        json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for nombre, rangos in (("base RRF", base_rangos), ("LLM", llm_rangos)):
        m = lab.metricas_rango(rangos)
        print(f"{nombre:9} " + "  ".join(f"{k} {v:.3f}" for k, v in m.items()))
    gana = sum(1 for b, n in zip(base_rangos, llm_rangos, strict=True) if (n or 99) <= 5 < (b or 99))
    pierde = sum(1 for b, n in zip(base_rangos, llm_rangos, strict=True) if (b or 99) <= 5 < (n or 99))
    print(f"top-5: el LLM gana {gana} casos y pierde {pierde}")
    print(f"Costo real: {usd:.3f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
