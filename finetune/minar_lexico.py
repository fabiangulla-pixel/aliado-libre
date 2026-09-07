"""Mina el puente entre cómo pregunta la gente y cómo habla la norma.

La idea viene de *The Vocabulary Gap Is an Equity Gap* (arXiv 2609.01645), que
con un puente hecho a mano ("food stamps" -> "supplemental nutrition assistance
program") subió el recall@5 de BM25 del 44% al 80% en consultas de prestaciones
sociales. Aquí no hace falta escribirlo a mano: el banco tiene 943 consultas
coloquiales emparejadas con el fragmento que de verdad las responde, así que el
puente se puede minar de los propios datos.

Cómo: para cada término coloquial se miran los términos que aparecen en los
fragmentos que lo responden, y se comparan con lo que ese término aparece en el
corpus en general. Lo que sube mucho por encima de su frecuencia de fondo es
candidato a traducción. Es información mutua puntual, la medida clásica para
esto.

Se mina SOLO con la partición dev. La de prueba no se toca, o el puente estaría
aprendido de las mismas consultas con las que luego se mide.

Uso:
    ./venv/Scripts/python.exe finetune/minar_lexico.py [--minimo 4]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

from index.buscar import PALABRAS_VACIAS  # noqa: E402

# Un término que sale en media docena de fragmentos no enseña nada; y uno que
# sale en la mitad del corpus tampoco discrimina.
MAX_TRADUCCIONES = 4


def _normalizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return [t for t in re.findall(r"\w+", texto) if len(t) > 3 and t not in PALABRAS_VACIAS]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--minimo", type=int, default=4, help="veces mínimas que debe verse un término")
    p.add_argument("--pares", default=str(RAIZ / "data" / "pares_embedding.jsonl"))
    p.add_argument("--salida", default=str(RAIZ / "eval" / "lexico.json"))
    args = p.parse_args()

    registros = [json.loads(linea) for linea in Path(args.pares).read_text(encoding="utf-8").splitlines()]
    print(f"{len(registros)} consultas de dev con su fragmento correcto")

    # Frecuencia de fondo: en cuántos fragmentos aparece cada término legal.
    # Se usan también los negativos, que son fragmentos reales del corpus y dan
    # una muestra mucho mayor sin costar nada.
    fondo: Counter[str] = Counter()
    documentos = 0
    for r in registros:
        for texto in [r["positivo"], *r["negativos"]]:
            documentos += 1
            fondo.update(set(_normalizar(texto)))

    # Coocurrencia: término coloquial de la consulta -> términos del fragmento
    # que la responde.
    juntos: dict[str, Counter[str]] = defaultdict(Counter)
    veces: Counter[str] = Counter()
    for r in registros:
        consulta = set(_normalizar(r["consulta"]))
        legales = set(_normalizar(r["positivo"]))
        for termino in consulta:
            veces[termino] += 1
            juntos[termino].update(legales - consulta)  # lo que la persona NO dijo

    lexico: dict[str, list[str]] = {}
    for termino, contador in juntos.items():
        if veces[termino] < args.minimo:
            continue
        puntuadas = []
        for legal, n in contador.items():
            if n < args.minimo or fondo[legal] < args.minimo:
                continue
            # información mutua puntual: cuánto sube este término legal cuando
            # aparece la palabra coloquial, frente a su frecuencia de fondo
            p_juntos = n / veces[termino]
            p_fondo = fondo[legal] / documentos
            if p_fondo <= 0:
                continue
            pmi = math.log(p_juntos / p_fondo)
            if pmi > 0:
                puntuadas.append((pmi * math.log(1 + n), legal))
        puntuadas.sort(reverse=True)
        traducciones = [legal for _, legal in puntuadas[:MAX_TRADUCCIONES]]
        if traducciones:
            lexico[termino] = traducciones

    Path(args.salida).write_text(json.dumps(lexico, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(lexico)} términos con traducción, en {args.salida}\n")
    print("Muestra (término coloquial -> lo que dice la norma):")
    for termino in sorted(lexico, key=lambda t: -veces[t])[:15]:
        print(f"  {termino:18} -> {', '.join(lexico[termino])}")


if __name__ == "__main__":
    main()
