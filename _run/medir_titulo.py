"""Mide el experimento del encabezado (título antepuesto) contra la línea base.

Lo lanza _run/al_terminar_titulo.ps1 al acabar el reindexado. Escribe
_run/INFORME_titulo.md. No gasta: solo búsqueda local.

Una sola variable: mismo corpus (1199645cc8a5a1ce), mismo troceo, mismo modelo,
misma GPU, mismas consultas. Solo cambia si el título se codificó con el texto.
"""

import os
import pickle
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# MEDIR_DIR_INDICE / MEDIR_CACHE solo para probar el propio medidor contra el
# índice de producción: debe reproducir la línea base exacta.
DIR_TITULO = str(RAIZ / "index" / "chroma_db_titulo")
os.environ["ALIADO_DIR_INDICE"] = os.environ.get("MEDIR_DIR_INDICE") or DIR_TITULO
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "finetune" / "eval"))

import lab_recuperacion as lab  # noqa: E402

CACHE_BASE = lab.CACHE
CACHE_TITULO = lab.CACHE.with_name(os.environ.get("MEDIR_CACHE") or "cache_candidatos_titulo.pkl")
INFORME = RAIZ / "_run" / (os.environ.get("MEDIR_INFORME") or "INFORME_titulo.md")


def main() -> None:
    lab.CACHE = CACHE_TITULO
    lab.cachear()
    base = pickle.loads(CACHE_BASE.read_bytes())
    titulo = pickle.loads(CACHE_TITULO.read_bytes())
    casos = lab.casos_anclados()

    def cfg(d):
        return lab.fusionar(d["vectorial"], d["fts"], 0.8)

    def solo_vec(d):
        return d["vectorial"]

    lineas = [
        "# Experimento: título antepuesto al codificar (ALIADO_ENCABEZADO=titulo)",
        "",
        "Corpus 1199645cc8a5a1ce, mismas 95 anclas, misma GPU. Generado solo por",
        "_run/medir_titulo.py al terminar el reindexado.",
        "",
        "| partición | config | recall@1 | recall@5 | recall@10 | MRR@10 |",
        "|---|---|---|---|---|---|",
    ]
    for sub in ("dev", "test", None):
        for nombre, cache in (("base", base), ("título", titulo)):
            for etiqueta, f in (("híbrida", cfg), ("solo vectorial", solo_vec)):
                m = lab.evaluar(cache, casos, f, sub)["metricas"]
                lineas.append(
                    f"| {sub or 'todo'} | {nombre} {etiqueta} | {m['recall@1']:.1%} | {m['recall@5']:.1%} "
                    f"| {m['recall@10']:.1%} | {m['mrr@10']:.3f} |"
                )
    lineas += ["", "## Por perfil (todo, híbrida, recall@5)", ""]
    lineas += ["| perfil | base | título |", "|---|---|---|"]
    rb = lab.evaluar(base, casos, cfg, None)["por_perfil"]
    rt = lab.evaluar(titulo, casos, cfg, None)["por_perfil"]
    for p in sorted(rb):
        lineas.append(f"| {p} | {rb[p][0]}/{rb[p][1]} | {rt.get(p, (0, 0))[0]}/{rt.get(p, (0, 0))[1]} |")

    rangos = []
    for c in casos:
        if c["id"] in base and c["id"] in titulo:
            rangos.append(
                (
                    lab.rango_documento(cfg(base[c["id"]]), c["documento_id"]),
                    lab.rango_documento(cfg(titulo[c["id"]]), c["documento_id"]),
                )
            )
    gana = sum(1 for b, t in rangos if (t or 99) <= 5 < (b or 99))
    pierde = sum(1 for b, t in rangos if (b or 99) <= 5 < (t or 99))
    lineas += ["", f"**Top-5 por caso: el título gana {gana} y pierde {pierde}** (de {len(rangos)}).", ""]
    INFORME.write_text("\n".join(lineas), encoding="utf-8")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
