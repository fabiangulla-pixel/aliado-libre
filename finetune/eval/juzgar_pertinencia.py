#!/usr/bin/env python3
"""Métrica con TODOS los documentos que responden, no solo el ancla.

El recall por ancla subcuenta: de 100 "fallos" auditados el 12-sep, 78 tenían
otro documento que sí respondía (p. ej. un concepto que cita el art. 51 de la
Ley 1480 en vez de la ley misma). Su techo es ~75%: un 90% no se puede medir con
ella.

Método (pooling, como en TREC): para cada consulta del piloto se juntan los
fragmentos que cada sistema pone en su top-10 — producción y cada variante del
reordenamiento amplio — y un LLM juzga cada fragmento una vez:
  2 = responde la pregunta (trae la regla que la resuelve)
  1 = relacionado pero no basta para responder
  0 = no sirve
Con esos juicios, por sistema: éxito@5 (algún fragmento del top-5 responde) y
nDCG@10. El ancla cuenta siempre como 2.

⚠️ El juez es un LLM: **hipótesis hasta que una persona revise la muestra**
(`--hoja` genera `revision_pertinencia.html`, con el veredicto oculto). Ver
[[feedback_verdad_de_referencia_humana_o_no_hay_metrica]].

Uso:
    .venv/Scripts/python.exe finetune/eval/juzgar_pertinencia.py            # estima
    .venv/Scripts/python.exe finetune/eval/juzgar_pertinencia.py --ejecutar
    .venv/Scripts/python.exe finetune/eval/juzgar_pertinencia.py --informe
    .venv/Scripts/python.exe finetune/eval/juzgar_pertinencia.py --hoja
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import random
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lab_recuperacion as lab  # noqa: E402
import reordenar_amplio as ra  # noqa: E402

JUEZ = "claude-sonnet-5"
EXTRACTO = 1200
JUICIOS = RAIZ / "finetune" / "eval" / "juicios_pertinencia.json"
HOJA = RAIZ / "finetune" / "eval" / "revision_pertinencia.html"

SISTEMA = """Eres un abogado colombiano que evalúa un buscador jurídico. Recibes la pregunta \
de una persona y una lista numerada de fragmentos de normas, sentencias o conceptos. \
Para CADA fragmento decide:
2 = el fragmento responde la pregunta: contiene la regla, derecho, plazo o procedimiento \
que resuelve lo que la persona pregunta (aunque sea en un concepto o sentencia que cita \
la norma).
1 = trata el mismo tema pero no basta para responder.
0 = no sirve para esta pregunta.
Sé exigente: "mismo tema" no es responder. Devuelve SOLO un objeto JSON \
{"numero": nota, ...} con todos los fragmentos, por ejemplo {"1": 2, "2": 0}."""


def sistemas() -> dict[str, dict[str, list[str]]]:
    """Top-10 de fragmentos por sistema y consulta."""
    cache = pickle.loads(lab.CACHE.read_bytes())
    salida: dict[str, dict[str, list[str]]] = {
        "produccion": {cid: lab.fusionar(d["vectorial"], d["fts"], 0.8)[:10] for cid, d in cache.items()}
    }
    for ruta in sorted(ra.DIR_SALIDA.glob("avance_*.json")):
        nombre = ruta.stem.removeprefix("avance_")
        av = json.loads(ruta.read_text(encoding="utf-8"))
        tops = {}
        for cid, reg in av.items():
            if "pool" not in reg:
                continue
            pool = reg["pool"]
            elegidos = [pool[i - 1] for i in ra.interpretar(reg["salida_ordenar"], len(pool))]
            tops[cid] = (elegidos + [f for f in pool if f not in elegidos])[:10]
        if tops:
            salida[nombre] = tops
    # Reordenadores locales (finetune/destilar/evaluar_reordenador.py): ya traen su top-10.
    for ruta in sorted((Path(__file__).resolve().parent / "sistemas_locales").glob("*.json")):
        salida[ruta.stem] = json.loads(ruta.read_text(encoding="utf-8"))
    return salida


def pares_a_juzgar(sis) -> dict[str, list[str]]:
    por_consulta: dict[str, list[str]] = {}
    for tops in sis.values():
        for cid, frags in tops.items():
            lista = por_consulta.setdefault(cid, [])
            lista.extend(f for f in frags if f not in lista)
    return por_consulta


def ndcg(notas: list[int], ideal: list[int], k: int = 10) -> float:
    def dcg(xs):
        return sum((2**x - 1) / math.log2(i + 2) for i, x in enumerate(xs[:k]))

    mejor = dcg(sorted(ideal, reverse=True))
    return dcg(notas) / mejor if mejor else 0.0


def informe(sis, juicios, casos) -> None:
    ancla = {c["id"]: c["documento_id"] for c in casos}
    reparto = lab.particion()

    def nota(cid, f):
        if lab.documento_de(f) == ancla.get(cid):
            return 2
        return juicios.get(cid, {}).get(f, 0)

    print(
        "éxito@5 = algún fragmento del top-5 responde (nota 2). Juez LLM: hipótesis hasta revisión humana.\n"
    )
    print(
        f"{'sistema':34} {'n':>3} {'éxito@1':>8} {'éxito@5':>8} {'éxito@10':>9} {'nDCG@10':>8}"
        "  dev/test éxito@5"
    )
    for nombre, tops in sis.items():
        ids = [cid for cid in tops if cid in ancla]
        if not ids:
            continue
        res = {}
        for k in (1, 5, 10):
            res[k] = sum(any(nota(cid, f) == 2 for f in tops[cid][:k]) for cid in ids) / len(ids)
        nd = sum(
            ndcg([nota(cid, f) for f in tops[cid]], [nota(cid, f) for f in juicios.get(cid, {})] + [2])
            for cid in ids
        ) / len(ids)
        partes = []
        for sub in ("dev", "test"):
            s = [cid for cid in ids if reparto.get(ancla[cid]) == sub]
            if s:
                partes.append(
                    f"{sum(any(nota(c, f) == 2 for f in tops[c][:5]) for c in s) / len(s) * 100:.0f}%"
                )
        print(
            f"{nombre:34} {len(ids):>3} {res[1] * 100:7.1f}% {res[5] * 100:7.1f}% {res[10] * 100:8.1f}% "
            f"{nd:8.3f}  {' / '.join(partes)}"
        )


def hoja(juicios, casos, n=40) -> None:
    """Muestra estratificada (por nota del juez) para revisión humana.

    El veredicto del juez solo se muestra cuando la persona juzgó todos los pares;
    la página guarda las respuestas en el navegador y calcula el acuerdo y kappa.
    """
    por_id = {c["id"]: c for c in casos}
    muestra = []
    rng = random.Random(2026)
    for nota_buscada in (2, 1, 0):
        candidatos = [(cid, f) for cid, js in juicios.items() for f, v in js.items() if v == nota_buscada]
        rng.shuffle(candidatos)
        muestra += candidatos[: n // 3 + (1 if nota_buscada == 2 else 0)]
    rng.shuffle(muestra)

    import chromadb

    from index.buscar import COLECCION, DIR_INDICE

    col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    datos = col.get(ids=[f for _, f in muestra], include=["documents", "metadatas"])
    texto = dict(zip(datos["ids"], datos["documents"], strict=True))
    meta = dict(zip(datos["ids"], datos["metadatas"], strict=True))
    pares = [
        {
            "n": i,
            "cid": cid,
            "fid": f,
            "consulta": por_id[cid]["consulta"],
            "titulo": (meta.get(f) or {}).get("titulo_documento") or f,
            "url": (meta.get(f) or {}).get("url_original") or "",
            "texto": (texto.get(f) or "")[:3000],
            "juez": juicios[cid][f],
        }
        for i, (cid, f) in enumerate(muestra, 1)
    ]
    datos_json = json.dumps({"version": "2026-10-03", "pares": pares}, ensure_ascii=False)
    # Evita que un "</script>" dentro de un fragmento cierre el bloque de código.
    datos_json = datos_json.replace("</", r"<\/")
    plantilla = (Path(__file__).resolve().parent / "plantilla_revision_pertinencia.html").read_text(
        encoding="utf-8"
    )
    HOJA.write_text(plantilla.replace("__DATOS__", datos_json), encoding="utf-8")
    print(f"Hoja de revisión: {HOJA} ({len(muestra)} pares)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ejecutar", action="store_true")
    ap.add_argument("--informe", action="store_true")
    ap.add_argument("--hoja", action="store_true")
    a = ap.parse_args()

    casos = lab.casos_anclados()
    sis = sistemas()
    pares = pares_a_juzgar(sis)
    juicios: dict = json.loads(JUICIOS.read_text(encoding="utf-8")) if JUICIOS.exists() else {}
    pendientes = {cid: [f for f in fs if f not in juicios.get(cid, {})] for cid, fs in pares.items()}
    pendientes = {cid: fs for cid, fs in pendientes.items() if fs}
    n_frag = sum(len(v) for v in pendientes.values())

    if a.informe:
        informe(sis, juicios, casos)
        return 0
    if a.hoja:
        hoja(juicios, casos)
        return 0

    from index import costos

    ent, sal = costos.PRECIOS[JUEZ]
    estimado = (n_frag * 380 * ent + len(pendientes) * 1200 * sal) / 1e6
    print(f"sistemas: {', '.join(sis)}")
    print(
        f"{n_frag} fragmentos por juzgar en {len(pendientes)} consultas | {JUEZ}"
        f" | estimado {estimado:.2f} USD"
    )
    if not a.ejecutar:
        print("No se llamó a ninguna API. Añade --ejecutar.")
        return 0

    import anthropic
    import chromadb

    from finetune.clave_api import leer_clave
    from index.buscar import COLECCION, DIR_INDICE

    cliente = anthropic.Anthropic(api_key=leer_clave(obligatoria=True))
    col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
    consulta_de = {c["id"]: c["consulta"] for c in casos}
    usd = 0.0
    for n, (cid, frags) in enumerate(pendientes.items(), 1):
        datos = col.get(ids=frags, include=["documents", "metadatas"])
        texto = dict(zip(datos["ids"], datos["documents"], strict=True))
        meta = dict(zip(datos["ids"], datos["metadatas"], strict=True))
        frags = [f for f in frags if f in texto]
        lineas = [
            f"[{i}] {(meta.get(f) or {}).get('titulo_documento', '')}\n"
            + re.sub(r"\s+", " ", texto[f] or "")[:EXTRACTO]
            for i, f in enumerate(frags, 1)
        ]
        prompt = f"Pregunta: {consulta_de[cid]}\n\nFragmentos:\n\n" + "\n\n".join(lineas)
        salida, uso = ra.llamar(cliente, JUEZ, SISTEMA, prompt)[:2]
        usd += costos.liquidar(uso, JUEZ).usd
        m = re.search(r"\{.*\}", salida, re.S)
        notas = json.loads(m.group(0)) if m else {}
        js = juicios.setdefault(cid, {})
        for i, f in enumerate(frags, 1):
            v = notas.get(str(i))
            if v in (0, 1, 2):
                js[f] = v
        JUICIOS.write_text(json.dumps(juicios, ensure_ascii=False, indent=1), encoding="utf-8")
        if n % 10 == 0:
            print(f"  {n}/{len(pendientes)}  {usd:.2f} USD", flush=True)
    print(f"Costo real: {usd:.3f} USD")
    informe(sis, juicios, casos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
