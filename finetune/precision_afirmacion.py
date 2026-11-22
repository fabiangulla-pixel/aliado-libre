"""¿Cumple la politica de afirmar? Precision y cobertura de la confianza "alta".

Meta (22-nov-2026): cuando la app NOMBRA una norma como la del caso, acierta
al menos 9 de cada 10 veces. En el resto presenta opciones.

Lee una corrida de `finetune/medir_dev.py` (que guarda la confianza por caso) y
la hoja que adjudica una persona (`finetune/eval/revision/adjudicar_piloto.csv`,
columna "sirve (si/no)"). Da dos cifras:

- estricta: solo cuenta como acierto lo que el banco ya aceptaba;
- adjudicada: ademas, lo que la persona marco "si". Un juicio de IA NO entra
  aqui: sin revision humana, la cifra que vale es la estricta.

    python finetune/precision_afirmacion.py fusion_amp_enr [piloto]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8")
HOJA = RAIZ / "finetune" / "eval" / "revision" / "adjudicar_piloto.csv"
META = 0.90


def _claves(*textos: str) -> set:
    """Formas de reconocer un documento: su id corto y la norma que es."""
    from index.normas import norma

    out: set = set()
    for t in textos:
        if t:
            out.add(t.split(":", 1)[-1] if t.startswith("legalize_co_github:") else t)
            n = norma(t)
            if n and t.lower().lstrip().startswith(("ley", "decreto", "codigo", "código", "legalize")):
                out.add(n)
    return out


def adjudicados() -> dict[str, dict]:
    """caso -> {clave del documento: True ("si") | False ("no")}; vacio = sin revisar."""
    if not HOJA.exists():
        return {}
    out: dict[str, dict] = {}
    with HOJA.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            marca = (r.get("sirve (si/no)") or "").strip().lower()
            if not marca:
                continue
            for k in _claves(r["documento_propuesto"], r["titulo"]):
                out.setdefault(r["caso"], {})[k] = marca.startswith("s")
    return out


def _veredicto(f: dict, si: dict) -> bool | None:
    """True/False si una persona adjudico el primer documento de esta fila."""
    marcas = si.get(f["id"], {})
    for k in _claves(f["ids"][0] if f.get("ids") else ""):
        if k in marcas:
            return marcas[k]
    return None


def main(etiqueta: str, banco: str = "piloto") -> None:
    filas = json.loads(
        (RAIZ / "finetune" / "eval" / "dev" / f"{banco}_{etiqueta}.json").read_text(encoding="utf-8")
    )["filas"]
    if not any("confianza" in f for f in filas):
        sys.exit("Esta corrida no guardo la confianza: vuelve a correrla con medir_dev.py.")
    si = adjudicados()
    n = len(filas)
    afirma = [f for f in filas if f.get("confianza") == "alta"]
    estricta = sum(f["uno"] is not None for f in afirma)
    adjud = sum(f["uno"] is not None or _veredicto(f, si) is True for f in afirma)
    pendientes = sum(f["uno"] is None and _veredicto(f, si) is None for f in afirma)
    print(f"{etiqueta} ({banco}, {n} preguntas)")
    print(f"  afirma una norma en {len(afirma)} ({len(afirma) / n * 100:.0f}% de las preguntas)")
    if not afirma:
        return
    for nombre, ok in (("estricta", estricta), ("adjudicada", adjud)):
        p = ok / len(afirma)
        marca = "CUMPLE" if p >= META else "no cumple"
        print(
            f"  precision {nombre:10}: {ok}/{len(afirma)} = {p * 100:.0f}%  [{marca} la meta de {META:.0%}]"
        )
    if pendientes:
        print(f"  {pendientes} afirmaciones fuera del banco sin adjudicar: ver {HOJA.name}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
