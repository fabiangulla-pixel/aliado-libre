"""Compara variantes del recuperador sobre LA MISMA submuestra, en una corrida.

Por qué existe: medir cada variante en una corrida distinta invita a confundir
dos cambios (pasó: una medición mezclaba el filtro de palabras vacías con la
reescritura de consultas, y su resultado no podía atribuirse a ninguno). Aquí
las variantes se evalúan sobre las mismas consultas, con el índice cargado una
sola vez, y la comparación queda pareada.

Variantes:
  crudo       tokenización original (toda palabra es un término OR)
  filtrado    sin palabras vacías y topando términos (el comportamiento actual)
  reescrito   filtrado + reescritura de la consulta con el modelo local

Uso:
    ./venv/Scripts/python.exe finetune/comparar_recuperadores.py
        [--por-perfil 20] [--variantes crudo,filtrado]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

TOPES = (1, 5, 8)


def _submuestra(banco: list[dict], por_perfil: int) -> list[dict]:
    """Mismas consultas para todas las variantes, equilibradas por perfil."""
    agrupado: dict[str, list] = defaultdict(list)
    for c in banco:
        agrupado[c["perfil"]].append(c)
    return [c for lista in agrupado.values() for c in lista[:por_perfil]]


def _acierto(resultados: list[dict], caso: dict, k: int) -> bool:
    for r in resultados[:k]:
        if r.get("id") == caso["fragmento_id"]:
            return True
        if caso.get("documento_id") and r.get("documento_id") == caso["documento_id"]:
            return True
    return False


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--por-perfil", type=int, default=20)
    p.add_argument("--variantes", default="crudo,filtrado,reescrito")
    p.add_argument("--salida", default=str(RAIZ / "eval" / "comparacion_recuperadores.json"))
    args = p.parse_args()
    variantes = [v.strip() for v in args.variantes.split(",") if v.strip()]

    banco = json.loads((RAIZ / "eval" / "banco_coloquial.json").read_text(encoding="utf-8"))
    casos = _submuestra(banco, args.por_perfil)
    print(f"{len(casos)} consultas ({args.por_perfil} por perfil) | variantes: {', '.join(variantes)}")

    from index import buscar as B

    filtrado = B._tokenizar

    def crudo(texto: str) -> list[str]:
        """La tokenización anterior al filtro, para tener el 'antes' exacto."""
        return re.findall(r"\w+", texto.lower())

    print("Cargando índice...")
    t0 = time.time()
    indice = B.IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s")

    resumen: dict[str, dict] = {}
    detalle: dict[str, list] = {}

    for variante in variantes:
        B._tokenizar = crudo if variante == "crudo" else filtrado
        reescribir = None
        if variante == "reescrito":
            from index.reescribir_consulta import reescribir_o_original as reescribir

        glob = {"total": 0, **dict.fromkeys(TOPES, 0)}
        perfiles = defaultdict(lambda: {"total": 0, **dict.fromkeys(TOPES, 0)})
        filas = []
        t0 = time.time()
        for i, caso in enumerate(casos, 1):
            consulta = reescribir(caso["consulta"]) if reescribir else caso["consulta"]
            res = indice.buscar(consulta, k=max(TOPES))
            fila = {
                "pregunta": caso["consulta"],
                "usada": consulta,
                "perfil": caso["perfil"],
                "fuente": caso["fuente"],
                "n_resultados": len(res),
                "puntajes": [r.get("puntaje") for r in res[:3]],
            }
            for k in TOPES:
                ok = _acierto(res, caso, k)
                fila[f"acierto@{k}"] = ok
                if ok:
                    glob[k] += 1
                    perfiles[caso["perfil"]][k] += 1
            glob["total"] += 1
            perfiles[caso["perfil"]]["total"] += 1
            filas.append(fila)
            if i % 40 == 0:
                print(f"  [{variante}] {i}/{len(casos)} @5={glob[5] / glob['total'] * 100:.0f}%")
        segundos = time.time() - t0
        resumen[variante] = {
            "global": dict(glob),
            "por_perfil": {k: dict(v) for k, v in perfiles.items()},
            "segundos_por_consulta": segundos / max(1, len(casos)),
        }
        detalle[variante] = filas
        print(f"  [{variante}] hecho en {segundos / 60:.1f} min ({segundos / len(casos):.2f} s/consulta)")

    B._tokenizar = filtrado

    print("\n" + "=" * 62)
    print(f"{'variante':12} {'s/consulta':>11} " + " ".join(f"{'@' + str(k):>7}" for k in TOPES))
    for v in variantes:
        g = resumen[v]["global"]
        celdas = " ".join(f"{g[k] / g['total'] * 100:6.1f}%" for k in TOPES)
        print(f"{v:12} {resumen[v]['segundos_por_consulta']:>10.2f}s {celdas}")

    print("\nrecall@5 por perfil:")
    perfiles = sorted(resumen[variantes[0]]["por_perfil"])
    print(f"  {'perfil':24} " + " ".join(f"{v:>11}" for v in variantes))
    for perfil in perfiles:
        celdas = []
        for v in variantes:
            d = resumen[v]["por_perfil"][perfil]
            celdas.append(f"{d[5] / d['total'] * 100:10.0f}%")
        print(f"  {perfil:24} " + " ".join(celdas))

    Path(args.salida).write_text(
        json.dumps({"resumen": resumen, "detalle": detalle}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nDetalle en {args.salida}")


if __name__ == "__main__":
    main()
