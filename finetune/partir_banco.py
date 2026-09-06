"""Parte el banco coloquial en desarrollo y prueba, sin fugas.

Por qué importa: vamos a probar varias palancas sobre la recuperación (modelo
de embeddings, pesos de fusión, umbral de abstención, reranker). Si se calibran
y se miden sobre las mismas consultas, el número sube sin que el producto
mejore — se estaría ajustando al banco, no a la realidad.

La partición es **por documento ancla**, no por consulta. Las 8 consultas de un
mismo fragmento (una por perfil) preguntan lo mismo con distintas palabras: si
unas cayeran en desarrollo y otras en prueba, el conjunto de prueba dejaría de
ser información nueva. Se agrupa por `documento_id` porque el acierto se cuenta
a nivel de documento, así que dos fragmentos del mismo decreto tampoco pueden
quedar separados.

Uso:
    ./venv/Scripts/python.exe finetune/partir_banco.py [--prueba 0.4]
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BANCO = RAIZ / "eval" / "banco_coloquial.json"
SEMILLA = 20260906  # fija: la partición tiene que ser la misma entre corridas


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prueba", type=float, default=0.4, help="proporción de documentos apartados")
    args = p.parse_args()

    banco = json.loads(BANCO.read_text(encoding="utf-8"))

    # agrupar por documento: la unidad de partición no es la consulta
    por_documento: dict[str, list] = defaultdict(list)
    for c in banco:
        por_documento[c["documento_id"] or c["fragmento_id"]].append(c)

    documentos = sorted(por_documento)
    random.Random(SEMILLA).shuffle(documentos)
    corte = int(len(documentos) * (1 - args.prueba))
    docs_dev, docs_prueba = documentos[:corte], documentos[corte:]

    dev = [c for d in docs_dev for c in por_documento[d]]
    prueba = [c for d in docs_prueba for c in por_documento[d]]

    solapan = set(docs_dev) & set(docs_prueba)
    assert not solapan, f"fuga: {len(solapan)} documentos en ambos lados"

    for nombre, conjunto, docs in (("dev", dev, docs_dev), ("prueba", prueba, docs_prueba)):
        salida = RAIZ / "eval" / f"banco_coloquial_{nombre}.json"
        salida.write_text(json.dumps(conjunto, ensure_ascii=False, indent=2), encoding="utf-8")
        perfiles = Counter(c["perfil"] for c in conjunto)
        print(
            f"{nombre:7} {len(conjunto):>5} consultas | {len(docs):>4} documentos | "
            f"perfiles entre {min(perfiles.values())} y {max(perfiles.values())}"
        )
        print(f"        -> {salida}")

    print(
        "\nRegla: se calibra y se experimenta SOLO con dev. El conjunto de prueba se mide\n"
        "una vez, al final, para reportar. Medir sobre prueba mientras se ajusta lo\n"
        "convierte en otro conjunto de desarrollo y deja de valer."
    )


if __name__ == "__main__":
    main()
