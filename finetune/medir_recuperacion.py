"""Mide la recuperación (no la redacción) sobre un banco de consultas ancladas.

Determinista y sin API: cada consulta del banco nació de un fragmento concreto,
así que el acierto es simplemente si la búsqueda lo devuelve entre los primeros
k. No hay juez ni coste.

Se cuenta acierto si aparece el fragmento exacto O cualquier otro fragmento del
MISMO documento: trocear un artículo en fragmentos es una decisión del pipeline,
ajena a la pregunta, y el corpus repite normas entre fuentes.

Con --reescribir, la consulta pasa antes por index/reescribir_consulta.py (el
modelo local). Eso permite comparar el mismo banco antes y después sin tocar
nada más.

Uso:
    ./venv/Scripts/python.exe finetune/medir_recuperacion.py [--banco X] [--reescribir] [--limite N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

TOPES = (1, 5, 8)


def _acierto(resultados: list[dict], caso: dict, k: int) -> bool:
    for r in resultados[:k]:
        if r.get("id") == caso["fragmento_id"]:
            return True
        if caso.get("documento_id") and r.get("documento_id") == caso["documento_id"]:
            return True
    return False


def _tabla(titulo: str, filas: dict[str, dict]) -> None:
    print(f"\n{titulo}")
    ancho = max((len(n) for n in filas), default=10)
    cabecera = "  ".join(f"@{k}" for k in TOPES)
    print(f"  {'':{ancho}}  {'n':>4}  {cabecera}")
    for nombre, d in sorted(filas.items(), key=lambda x: -x[1]["total"]):
        total = d["total"] or 1
        celdas = "  ".join(f"{d[k] / total * 100:4.0f}%" for k in TOPES)
        print(f"  {nombre:{ancho}}  {d['total']:>4}  {celdas}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial.json"))
    p.add_argument(
        "--reescribir", action="store_true", help="reescribir la consulta con el modelo local antes de buscar"
    )
    p.add_argument("--limite", type=int, default=0, help="usar solo las primeras N consultas")
    p.add_argument("--salida", default="", help="archivo JSON donde guardar el detalle")
    args = p.parse_args()

    casos = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    if args.limite:
        # recorta manteniendo el equilibrio entre perfiles: cortar en seco
        # dejaría fuera perfiles enteros, porque el banco va agrupado
        por_perfil: dict[str, list] = defaultdict(list)
        for c in casos:
            por_perfil[c["perfil"]].append(c)
        cupo = max(1, args.limite // max(1, len(por_perfil)))
        casos = [c for lista in por_perfil.values() for c in lista[:cupo]]

    print(f"{len(casos)} consultas | reescritura: {'SI' if args.reescribir else 'NO'}")

    from index.buscar import IndiceBusqueda

    print("Cargando índice...")
    inicio = time.time()
    indice = IndiceBusqueda()
    print(f"Índice listo en {time.time() - inicio:.0f}s")

    reescribir = None
    if args.reescribir:
        from index.reescribir_consulta import reescribir as _r

        reescribir = _r

    global_ = {"total": 0, **dict.fromkeys(TOPES, 0)}
    por_perfil = defaultdict(lambda: {"total": 0, **dict.fromkeys(TOPES, 0)})
    por_fuente = defaultdict(lambda: {"total": 0, **dict.fromkeys(TOPES, 0)})
    detalle = []

    inicio = time.time()
    for i, caso in enumerate(casos, 1):
        consulta = caso["consulta"]
        consulta_usada = consulta
        if reescribir is not None:
            try:
                consulta_usada = reescribir(consulta)
            except Exception as e:  # noqa: BLE001
                consulta_usada = consulta
                if i == 1:
                    print(f"  aviso: la reescritura falló ({type(e).__name__}), se usa la consulta cruda")

        resultados = indice.buscar(consulta_usada, k=max(TOPES))
        fila = {"pregunta": consulta, "reescrita": consulta_usada, "perfil": caso["perfil"]}
        for k in TOPES:
            ok = _acierto(resultados, caso, k)
            fila[f"acierto@{k}"] = ok
            if ok:
                global_[k] += 1
                por_perfil[caso["perfil"]][k] += 1
                por_fuente[caso["fuente"]][k] += 1
        global_["total"] += 1
        por_perfil[caso["perfil"]]["total"] += 1
        por_fuente[caso["fuente"]]["total"] += 1
        detalle.append(fila)

        if i % 25 == 0 or i == len(casos):
            transcurrido = time.time() - inicio
            restante = transcurrido / i * (len(casos) - i) / 60
            print(
                f"  [{i}/{len(casos)}] @5={global_[5] / global_['total'] * 100:.0f}%  "
                f"(~{restante:.0f} min restantes)"
            )

    total = global_["total"] or 1
    print("\n" + "=" * 52)
    print(f"GLOBAL sobre {total} consultas" + ("  (con reescritura)" if args.reescribir else ""))
    for k in TOPES:
        print(f"  recall@{k}: {global_[k]}/{total} = {global_[k] / total * 100:.1f}%")
    _tabla("Por perfil de usuario:", por_perfil)
    _tabla("Por fuente:", por_fuente)

    salida = args.salida or str(
        RAIZ / "eval" / ("recuperacion_reescrita.json" if args.reescribir else "recuperacion_base.json")
    )
    Path(salida).write_text(
        json.dumps(
            {
                "reescritura": args.reescribir,
                "global": dict(global_),
                "por_perfil": {k: dict(v) for k, v in por_perfil.items()},
                "por_fuente": {k: dict(v) for k, v in por_fuente.items()},
                "detalle": detalle,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nDetalle en {salida}")


if __name__ == "__main__":
    main()
