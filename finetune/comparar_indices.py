"""Compara dos índices vectoriales sobre EL MISMO banco, en una sola corrida.

Sirve para responder la única pregunta que importa del reindexado: ¿el modelo
de embeddings nuevo encuentra el documento correcto más veces que el viejo?

Cada índice se carga en su propio proceso hijo. No es capricho:
`index/buscar.py` lee el modelo y la colección de variables de entorno **al
importarse**, así que dos configuraciones distintas no pueden convivir en el
mismo proceso sin recargar módulos a mano, que es frágil y engaña.

Se mide sobre el conjunto de DESARROLLO. El de prueba se reserva para reportar
una vez, al final: medirlo mientras se experimenta lo convierte en otro
conjunto de desarrollo y deja de significar nada.

Uso:
    ./venv/Scripts/python.exe finetune/comparar_indices.py [--limite 400]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import defaultdict
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PYTHON = RAIZ.parent / "venv" / "Scripts" / "python.exe"
TOPES = (1, 5, 8)

# (etiqueta, modelo de embeddings, colección de Chroma)
INDICES = [
    ("actual (MiniLM 128 tok)", "paraphrase-multilingual-MiniLM-L12-v2", "aliado_libre"),
    (
        "nuevo (e5-large 512 tok)",
        "intfloat/multilingual-e5-large",
        "aliado_libre_multilingual_e5_large",
    ),
]

HIJO = r"""
import json, sys
sys.path.insert(0, r"{raiz}")
from index.buscar import IndiceBusqueda

casos = json.load(open(r"{banco}", encoding="utf-8"))
indice = IndiceBusqueda()
salida = []
for caso in casos:
    res = indice.buscar(caso["consulta"], k={maxk})
    salida.append({{
        "perfil": caso["perfil"],
        "ids": [r.get("id") for r in res],
        "documentos": [r.get("documento_id") for r in res],
        "puntajes": [r.get("puntaje") for r in res[:3]],
    }})
print("__RESULTADOS__" + json.dumps(salida, ensure_ascii=False))
"""


def _correr(modelo: str, coleccion: str, banco: Path, maxk: int) -> list[dict]:
    entorno = dict(os.environ)
    entorno["ALIADO_MODELO_EMBEDDINGS"] = modelo
    entorno["ALIADO_COLECCION"] = coleccion
    codigo = HIJO.format(raiz=RAIZ.parent, banco=banco, maxk=maxk)
    proceso = subprocess.run(
        [str(PYTHON), "-c", codigo],
        env=entorno,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proceso.returncode != 0 or "__RESULTADOS__" not in proceso.stdout:
        print(proceso.stdout[-2000:])
        print(proceso.stderr[-3000:])
        raise SystemExit(f"El índice {coleccion} falló (código {proceso.returncode}).")
    return json.loads(proceso.stdout.split("__RESULTADOS__", 1)[1])


def _acierto(fila: dict, caso: dict, k: int) -> bool:
    if caso["fragmento_id"] in fila["ids"][:k]:
        return True
    doc = caso.get("documento_id")
    return bool(doc) and doc in fila["documentos"][:k]


def _mcnemar(a: list[bool], b: list[bool]) -> tuple[int, int, float]:
    solo_a = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    solo_b = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n, menor = solo_a + solo_b, min(solo_a, solo_b)
    if n == 0:
        return solo_a, solo_b, 1.0
    p = sum(comb(n, i) for i in range(menor + 1)) / 2**n * 2
    return solo_a, solo_b, min(p, 1.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_dev.json"))
    p.add_argument("--limite", type=int, default=0, help="usar solo N consultas (equilibradas)")
    p.add_argument("--salida", default=str(RAIZ / "eval" / "comparacion_indices.json"))
    args = p.parse_args()

    casos = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    if args.limite:
        por_perfil: dict[str, list] = defaultdict(list)
        for c in casos:
            por_perfil[c["perfil"]].append(c)
        cupo = max(1, args.limite // max(1, len(por_perfil)))
        casos = [c for lista in por_perfil.values() for c in lista[:cupo]]

    banco_tmp = RAIZ / "eval" / "_subconjunto_comparacion.json"
    banco_tmp.write_text(json.dumps(casos, ensure_ascii=False), encoding="utf-8")
    print(f"{len(casos)} consultas del conjunto de desarrollo\n")

    corridas: dict[str, list[dict]] = {}
    for etiqueta, modelo, coleccion in INDICES:
        print(f"Midiendo {etiqueta}... (carga el índice, tarda)")
        corridas[etiqueta] = _correr(modelo, coleccion, banco_tmp, max(TOPES))
        print("  hecho")

    aciertos: dict[str, dict[int, list[bool]]] = {}
    por_perfil_res: dict[str, dict[str, dict]] = {}
    for etiqueta, filas in corridas.items():
        aciertos[etiqueta] = {
            k: [_acierto(f, c, k) for f, c in zip(filas, casos, strict=True)] for k in TOPES
        }
        agrupado: dict[str, dict] = defaultdict(lambda: {"total": 0, **dict.fromkeys(TOPES, 0)})
        for f, c in zip(filas, casos, strict=True):
            agrupado[c["perfil"]]["total"] += 1
            for k in TOPES:
                if _acierto(f, c, k):
                    agrupado[c["perfil"]][k] += 1
        por_perfil_res[etiqueta] = dict(agrupado)

    print("\n" + "=" * 64)
    print(f"{'índice':28} " + " ".join(f"{'@' + str(k):>8}" for k in TOPES))
    for etiqueta in corridas:
        celdas = " ".join(f"{sum(aciertos[etiqueta][k]) / len(casos) * 100:7.1f}%" for k in TOPES)
        print(f"{etiqueta:28} {celdas}")

    viejo, nuevo = INDICES[0][0], INDICES[1][0]
    print("\nContraste pareado (McNemar exacto):")
    for k in TOPES:
        a, b, pv = _mcnemar(aciertos[viejo][k], aciertos[nuevo][k])
        veredicto = "DIFERENCIA REAL" if pv < 0.05 else "no distinguible del ruido"
        print(f"  @{k}: solo el viejo {a}, solo el nuevo {b}, p={pv:.4f} -> {veredicto}")

    print("\nrecall@5 por perfil de usuario:")
    perfiles = sorted(por_perfil_res[viejo])
    print(f"  {'perfil':24} {'viejo':>8} {'nuevo':>8}")
    for perfil in perfiles:
        v = por_perfil_res[viejo][perfil]
        n = por_perfil_res[nuevo][perfil]
        print(f"  {perfil:24} {v[5] / v['total'] * 100:7.0f}% {n[5] / n['total'] * 100:7.0f}%")

    Path(args.salida).write_text(
        json.dumps(
            {
                "n": len(casos),
                "banco": args.banco,
                "global": {e: {str(k): sum(aciertos[e][k]) for k in TOPES} for e in corridas},
                "por_perfil": {e: por_perfil_res[e] for e in corridas},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    banco_tmp.unlink(missing_ok=True)
    print(f"\nDetalle en {args.salida}")


if __name__ == "__main__":
    main()
