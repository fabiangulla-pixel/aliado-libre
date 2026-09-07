"""Exporta los candidatos que ya recupera la búsqueda, para reordenarlos en GPU.

Colab no tiene el índice —son 21 GB y tardaría más en bajarlo que en hacer el
trabajo—, pero tampoco le hace falta: reordenar no consulta el corpus, solo lee
pares de pregunta y pasaje. Así que la búsqueda se hace aquí una sola vez y allá
solo se puntúa.

Se exportan más candidatos de los que se van a reordenar a propósito: la curva de
recall medida el 7-sep-2026 dice que el fragmento correcto está en el top-200 el
75% de las veces, contra el 59% en el top-40. Ese salto es el techo que el
reranker puede alcanzar, y es la razón de esta prueba.

Uso:
    ./venv/Scripts/python.exe finetune/exportar_candidatos.py [--por-perfil 25]
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

# Recortar el texto aquí y no allá: el archivo viaja por Drive y el reranker
# trunca a 512 tokens de todas formas.
MAX_CARACTERES = 2000


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--por-perfil", type=int, default=25)
    p.add_argument("--candidatos", type=int, default=200)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_prueba.json"))
    p.add_argument("--salida", default=str(RAIZ / "eval" / "candidatos_prueba.json"))
    args = p.parse_args()

    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    agrupado: dict[str, list] = defaultdict(list)
    for c in banco:
        agrupado[c["perfil"]].append(c)
    casos = [c for lista in agrupado.values() for c in lista[: args.por_perfil]]
    print(f"{len(casos)} consultas de {Path(args.banco).name}")

    from index.buscar import IndiceBusqueda

    print("Cargando índice...")
    t0 = time.time()
    indice = IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s")

    salida = []
    encontrados = 0
    t0 = time.time()
    for i, caso in enumerate(casos, 1):
        resultados = indice.buscar(caso["consulta"], k=args.candidatos)
        posicion = None
        for j, r in enumerate(resultados, 1):
            if r.get("id") == caso["fragmento_id"] or (
                caso.get("documento_id") and r.get("documento_id") == caso["documento_id"]
            ):
                posicion = j
                break
        encontrados += posicion is not None
        salida.append(
            {
                "consulta": caso["consulta"],
                "perfil": caso["perfil"],
                "fragmento_id": caso["fragmento_id"],
                "documento_id": caso.get("documento_id"),
                "posicion_original": posicion,
                "candidatos": [
                    {
                        "id": r.get("id"),
                        "documento_id": r.get("documento_id"),
                        "texto": (r.get("texto") or "")[:MAX_CARACTERES],
                    }
                    for r in resultados
                ],
            }
        )
        if i % 50 == 0:
            print(f"  {i}/{len(casos)} — {(time.time() - t0) / i:.1f} s/consulta")

    ruta = Path(args.salida)
    ruta.write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    mb = ruta.stat().st_size / 1024**2
    print(f"\n{len(salida)} consultas en {ruta} ({mb:.0f} MB)")
    print(
        f"El fragmento correcto está entre los {args.candidatos} candidatos en "
        f"{encontrados}/{len(casos)} ({encontrados / len(casos) * 100:.1f}%). "
        "Ese es el techo que el reranker no puede pasar."
    )


if __name__ == "__main__":
    main()
