"""¿Encuentra Aliado Libre la providencia de la Corte Suprema que se le cita?

Banco reproducible (semilla fija) de citas a providencias que SÍ están en el
índice, escritas de varias formas ("CSJ SL131-2026", "sentencia SL 131 de
2026", "SL-131-2026", "la SC016-2018 sobre…"), más citas a providencias que NO
están (numeración ficticia) y consultas reales sin cita (falsos positivos).

Compara:
  antes   la búsqueda híbrida sola (IndiceBusqueda.buscar, configuración por
          defecto): ¿el documento citado sale primero / entre los 5?
  ahora   el resolvedor de citas (index/resolver_citas.py), que es lo que la
          GUI y el MCP anteponen a la búsqueda.

No usa banco_prueba_200 ni ajusta nada con él: es un banco nuevo, de citas
exactas, que se puede regenerar.

    python finetune/medir_citas_suprema.py [n=60] [semilla=23]
    -> finetune/eval/citas_suprema/resultado_<fecha>.json
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import random
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.stdout.reconfigure(encoding="utf-8")

FORMAS = (
    "CSJ {p}{n}-{a}",
    "sentencia {p} {n} de {a}",
    "{p}-{n}-{a}",
    "qué dijo la Corte en la {p}{n}-{a} sobre este tema",
)


def banco(n: int, semilla: int) -> list[dict]:
    from index import providencias as P

    docs = P.catalogo()["documentos"]
    rng = random.Random(semilla)
    elegidos = rng.sample(sorted(d for d, f in docs.items() if f.get("canonica")), n)
    casos = []
    for i, did in enumerate(elegidos):
        r = P.referencias(docs[did]["canonica"])[0]
        forma = FORMAS[i % len(FORMAS)]
        num = str(r.numero) + r.letra
        casos.append(
            {"tipo": "en_indice", "consulta": forma.format(p=r.prefijo, n=num, a=r.anio), "esperado": did}
        )
    for i in range(max(5, n // 6)):  # FICTICIAS: numeración que la Corte no usa
        casos.append({"tipo": "no_esta", "consulta": f"CSJ SL{98000 + i}-2024", "esperado": None})
    reales = json.loads(
        (RAIZ / "finetune" / "eval" / "consultas_reales_google.json").read_text(encoding="utf-8")
    )
    for c in rng.sample(reales, min(len(reales), 3 * n)):
        casos.append({"tipo": "sin_cita", "consulta": c["consulta"], "esperado": None})
    return casos


def main(n: int = 60, semilla: int = 23) -> None:
    from index import providencias as P
    from index.buscar import IndiceBusqueda
    from index.resolver_citas import resolver

    casos = banco(n, semilla)
    # falsos positivos del reconocedor: solo texto, sin índice
    fp = [c["consulta"] for c in casos if c["tipo"] == "sin_cita" and P.parsear(c["consulta"])]

    ix = IndiceBusqueda()
    ix.buscar("calentamiento", k=5)
    col = ix._coleccion
    filas = []
    t0 = time.time()
    for c in casos:
        if c["tipo"] == "sin_cita":
            continue
        res = ix.buscar(c["consulta"], k=5)
        docs = [(r.get("documento_id") or r["id"].split("::")[0]) for r in res]
        rz = resolver(c["consulta"], col, k=5)
        docs_r = [(r.get("documento_id") or r["id"].split("::")[0]) for r in rz.resultados]
        filas.append(
            {
                **c,
                "antes_top1": bool(docs) and docs[0] == c["esperado"],
                "antes_top5": c["esperado"] in docs,
                "ahora_top1": bool(docs_r) and docs_r[0] == c["esperado"],
                "ahora_aviso": rz.aviso,
                "ahora_documentos": docs_r,
            }
        )
    en = [f for f in filas if f["tipo"] == "en_indice"]
    no = [f for f in filas if f["tipo"] == "no_esta"]
    resumen = {
        "fecha": _dt.datetime.now().isoformat(timespec="seconds"),
        "hardware": platform.processor() or platform.machine(),
        "configuracion": {k: v for k, v in os.environ.items() if k.startswith("ALIADO_")} or "por defecto",
        "catalogo_suprema": P.catalogo().get("generado"),
        "fragmentos_indice": ix._total,
        "n_en_indice": len(en),
        "antes_top1": sum(f["antes_top1"] for f in en),
        "antes_top5": sum(f["antes_top5"] for f in en),
        "ahora_top1": sum(f["ahora_top1"] for f in en),
        "no_esta_bien_avisado": sum(
            not f["ahora_documentos"] and "no está en el índice" in f["ahora_aviso"] for f in no
        ),
        "n_no_esta": len(no),
        "falsos_positivos_reconocedor": len(fp),
        "n_sin_cita": sum(c["tipo"] == "sin_cita" for c in casos),
        "ejemplos_falsos_positivos": fp[:10],
        "segundos": round(time.time() - t0, 1),
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    carpeta = RAIZ / "finetune" / "eval" / "citas_suprema"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"resultado_{_dt.date.today().isoformat()}.json").write_text(
        json.dumps({"resumen": resumen, "filas": filas}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main(*(int(x) for x in sys.argv[1:3]))
