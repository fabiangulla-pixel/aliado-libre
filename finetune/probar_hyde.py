"""Busca con el pasaje jurídico que un modelo IMAGINA, no con la pregunta.

El diagnóstico dice que el fallo es de vocabulario: la persona escribe "me
echaron estando incapacitado" y la norma dice "estabilidad laboral reforzada del
trabajador en situación de debilidad manifiesta". No se parecen en la superficie,
y el embedding compara superficies.

HyDE (Hypothetical Document Embeddings) le da la vuelta: se le pide a un modelo
que redacte cómo sonaría la norma que responde, y se busca con ESE texto. Deja de
comparar una pregunta con una norma y pasa a comparar una norma con otra norma.

No es lo mismo que la reescritura de consultas que ya se descartó. Aquella usaba
el modelo propio, que acierta poco y por eso tampoco sabía reformular
("impuesto de tiembre" -> "sueldo mensual salario fijo"). Aquí redacta un modelo
capaz, y no reformula la pregunta: inventa la respuesta.

Se mide contra la partición de PRUEBA, que no se usa para ajustar nada, y se
comparan tres cosas: la búsqueda de hoy, la búsqueda solo con el pasaje
imaginado, y la fusión de ambas — porque el texto imaginado puede acertar el
registro y equivocarse en el dato concreto, y entonces la pregunta original sigue
haciendo falta.

Uso:
    ./venv/Scripts/python.exe finetune/probar_hyde.py [--por-perfil 25]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

MODELO = "claude-haiku-4-5"
TOPES = (1, 5, 8)
K_RRF = 60  # mismo que index/buscar.py: la fusión debe ser comparable

PROMPT = """Un ciudadano colombiano pregunta esto:

"{consulta}"

Escribe el fragmento de una norma, sentencia o concepto oficial colombiano que
responderia esa duda. No respondas al ciudadano ni expliques nada: redacta el
texto legal en si, como aparecería en el Diario Oficial o en una sentencia.

Usa el vocabulario tecnico que de verdad usaria esa norma. Si no sabes cual es la
norma exacta, invéntala igual: lo que importa es el registro y los terminos, no
la exactitud de la cita.

Maximo 120 palabras. Responde solo con el texto legal."""


def _acierto(resultados: list[dict], caso: dict, k: int) -> bool:
    for r in resultados[:k]:
        if r.get("id") == caso["fragmento_id"]:
            return True
        if caso.get("documento_id") and r.get("documento_id") == caso["documento_id"]:
            return True
    return False


def _mcnemar(a: list[bool], b: list[bool]) -> tuple[int, int, float]:
    sa = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    sb = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n, menor = sa + sb, min(sa, sb)
    if n == 0:
        return sa, sb, 1.0
    return sa, sb, min(sum(comb(n, i) for i in range(menor + 1)) / 2**n * 2, 1.0)


def _fusionar(*listas: list[dict]) -> list[dict]:
    """Fusión recíproca de rangos, igual que la búsqueda híbrida ya existente."""
    puntaje: dict[str, float] = {}
    porid: dict[str, dict] = {}
    for lista in listas:
        for rango, r in enumerate(lista, 1):
            ident = r.get("id")
            if ident is None:
                continue
            puntaje[ident] = puntaje.get(ident, 0) + 1 / (K_RRF + rango)
            porid.setdefault(ident, r)
    return [porid[i] for i in sorted(puntaje, key=lambda x: -puntaje[x])]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--por-perfil", type=int, default=25)
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_prueba.json"))
    p.add_argument("--salida", default=str(RAIZ / "eval" / "hyde.json"))
    args = p.parse_args()

    clave = os.environ.get("ANTHROPIC_API_KEY")
    if not clave:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")

    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    agrupado: dict[str, list] = defaultdict(list)
    for c in banco:
        agrupado[c["perfil"]].append(c)
    casos = [c for lista in agrupado.values() for c in lista[: args.por_perfil]]
    print(f"{len(casos)} consultas apartadas")

    import anthropic

    from index.buscar import IndiceBusqueda
    from index.costos import liquidar

    cliente = anthropic.Anthropic(api_key=clave)
    print("Cargando índice...")
    t0 = time.time()
    indice = IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s")

    aciertos = {modo: {k: [] for k in TOPES} for modo in ("original", "hyde", "fusion")}
    gasto = 0.0
    imaginados = []
    t0 = time.time()
    for i, caso in enumerate(casos, 1):
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=300,
            messages=[{"role": "user", "content": PROMPT.format(consulta=caso["consulta"])}],
        )
        gasto += liquidar(respuesta.usage, MODELO).usd
        imaginado = "".join(b.text for b in respuesta.content if hasattr(b, "text")).strip()
        imaginados.append({"consulta": caso["consulta"], "imaginado": imaginado})

        res_original = indice.buscar(caso["consulta"], k=max(TOPES))
        res_hyde = indice.buscar(imaginado, k=max(TOPES)) if imaginado else []
        res_fusion = _fusionar(res_original, res_hyde)

        for modo, res in (("original", res_original), ("hyde", res_hyde), ("fusion", res_fusion)):
            for k in TOPES:
                aciertos[modo][k].append(_acierto(res, caso, k))

        if i % 25 == 0:
            print(f"  {i}/{len(casos)} — {gasto:.3f} USD — {(time.time() - t0) / i:.1f} s/consulta")

    n = len(casos)
    print("\n" + "=" * 52)
    print(f"{'modo':>10} " + " ".join(f"{'@' + str(k):>8}" for k in TOPES))
    for modo in ("original", "hyde", "fusion"):
        celdas = " ".join(f"{sum(aciertos[modo][k]) / n * 100:7.1f}%" for k in TOPES)
        print(f"{modo:>10} {celdas}")

    print("\nContraste pareado contra la búsqueda de hoy:")
    for modo in ("hyde", "fusion"):
        for k in TOPES:
            pierde, gana, pv = _mcnemar(aciertos["original"][k], aciertos[modo][k])
            print(
                f"  {modo:>6} @{k}: pierde {pierde:2}, gana {gana:2}, p={pv:.4f}"
                f" -> {'REAL' if pv < 0.05 else 'ruido'}"
            )

    print(f"\nCosto real: {gasto:.2f} USD ({MODELO}, {n} llamadas)")
    Path(args.salida).write_text(
        json.dumps(
            {
                "n": n,
                "modelo": MODELO,
                "usd": gasto,
                "aciertos": {m: {str(k): sum(v[k]) for k in TOPES} for m, v in aciertos.items()},
                "imaginados": imaginados[:20],
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"Detalle en {args.salida}")


if __name__ == "__main__":
    main()
