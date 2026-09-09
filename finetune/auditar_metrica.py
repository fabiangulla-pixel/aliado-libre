"""¿Cuántos "fallos" de la búsqueda lo son de verdad?

El banco marca UN fragmento como correcto: aquel del que se generó la pregunta.
Pero el corpus tiene 718.388 fragmentos y muchas preguntas las responde más de
uno — el mismo artículo repetido en otra norma, otra sentencia con la misma
doctrina, el concepto de una entidad distinta que dice lo mismo. Cuando la
búsqueda trae uno de esos, lo contamos como fallo.

Si eso pasa a menudo, **todas las cifras de recall del proyecto están
subestimadas** y el objetivo del 90% se está midiendo contra una vara torcida.
Esto no es una mejora: es comprobar si el termómetro funciona, y por eso va antes
que cualquier otra cosa.

Método: se toman los casos donde el fragmento ancla NO está entre los primeros
resultados, se le muestran al juez la pregunta y esos fragmentos, y se le pregunta
si alguno responde. El juez no ve cuál era el ancla, para que no pueda
conformarse con ella.

Uso:
    ./venv/Scripts/python.exe finetune/auditar_metrica.py [--casos 100]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

MODELO = "claude-haiku-4-5"
TOPE = 5  # los que el modelo lee de verdad

PROMPT = """Un ciudadano colombiano pregunta:

"{consulta}"

Estos son los documentos que le mostró un buscador jurídico:

{fragmentos}

¿Alguno de esos documentos responde la pregunta, aunque sea parcialmente?

Sé estricto: que hable del mismo tema NO basta. Tiene que contener información
que responda lo que la persona preguntó. Un documento sobre pensiones no
responde una pregunta sobre pensiones si no dice lo que la persona quiere saber.

Responde SOLO con JSON:
{{"responde": true/false, "cual": <numero del documento o null>, "razon": "una frase"}}"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--casos", type=int, default=100)
    p.add_argument("--candidatos", default=str(RAIZ / "eval" / "candidatos_prueba.json"))
    p.add_argument("--salida", default=str(RAIZ / "eval" / "auditoria_metrica.json"))
    args = p.parse_args()

    # Entorno o ~/.aliado_libre/credenciales.json; ver finetune/clave_api.py.
    from finetune.clave_api import leer_clave

    clave = leer_clave()

    datos = json.loads(Path(args.candidatos).read_text(encoding="utf-8"))
    fallos = [d for d in datos if not d["posicion_original"] or d["posicion_original"] > TOPE]
    print(f"{len(fallos)} de {len(datos)} consultas cuentan hoy como fallo en @{TOPE}")
    fallos = fallos[: args.casos]
    print(f"Se auditan {len(fallos)}")

    import anthropic

    from index.costos import liquidar

    cliente = anthropic.Anthropic(api_key=clave)

    respondidos = 0
    gasto = 0.0
    detalle = []
    for i, caso in enumerate(fallos, 1):
        trozos = caso["candidatos"][:TOPE]
        texto = "\n\n".join(f"--- Documento {j} ---\n{c['texto'][:1200]}" for j, c in enumerate(trozos, 1))
        r = cliente.messages.create(
            model=MODELO,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT.format(consulta=caso["consulta"], fragmentos=texto),
                }
            ],
        )
        gasto += liquidar(r.usage, MODELO).usd
        crudo = "".join(b.text for b in r.content if hasattr(b, "text")).strip()
        try:
            inicio, fin = crudo.index("{"), crudo.rindex("}") + 1
            juicio = json.loads(crudo[inicio:fin])
        except (ValueError, json.JSONDecodeError):
            juicio = {"responde": False, "razon": "el juez no devolvió JSON"}
        responde = bool(juicio.get("responde"))
        respondidos += responde
        detalle.append(
            {
                "consulta": caso["consulta"],
                "perfil": caso["perfil"],
                "responde": responde,
                "cual": juicio.get("cual"),
                "razon": juicio.get("razon", ""),
            }
        )
        if i % 20 == 0:
            print(f"  {i}/{len(fallos)} — {respondidos} respondidos — {gasto:.3f} USD")

    n = len(fallos)
    print("\n" + "=" * 52)
    print(f"Fallos auditados:            {n}")
    print(f"Alguno SÍ respondía:         {respondidos} ({respondidos / n * 100:.0f}%)")
    print(f"Fallo real (nadie respondía): {n - respondidos} ({(n - respondidos) / n * 100:.0f}%)")
    print(f"\nCosto real: {gasto:.2f} USD ({MODELO}, {n} llamadas)")
    Path(args.salida).write_text(
        json.dumps(
            {"n": n, "responden": respondidos, "usd": gasto, "detalle": detalle},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"Detalle en {args.salida}")


if __name__ == "__main__":
    main()
