"""Responde el mismo banco con un modelo grande, para saber a quién culpar.

El proyecto tiene dos números que no encajan: la búsqueda deja un documento útil
entre los cinco primeros en torno al 86% de las veces, y las respuestas del
modelo propio se juzgan correctas alrededor del 33%. Entre esos dos números hay
una caída de cincuenta puntos, y hasta ahora no sabíamos de quién es la culpa.

Esta prueba lo aísla: **los mismos fragmentos, el mismo prompt, la misma pregunta
y el mismo juez**; lo único que cambia es quién redacta. Si el modelo grande
acierta mucho más, la caída es del modelo pequeño y hay una decisión de producto
que tomar. Si acierta parecido, el problema está en los fragmentos o en el
prompt, y afinar modelos no lo va a arreglar.

Se reutiliza el archivo de respuestas ya generado con el modelo propio, que trae
los fragmentos exactos que recibió: sin eso no sería una comparación, sería otra
prueba distinta.

Uso:
    ./venv/Scripts/python.exe finetune/generar_respuestas_nube.py [--modelo claude-haiku-4-5]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

from index.responder import PROMPT_SISTEMA, _formatear_fragmentos  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--modelo", default="claude-haiku-4-5")
    p.add_argument("--entrada", default=str(RAIZ / "respuestas_gpu" / "respuestas_local_q8.json"))
    p.add_argument("--salida", default=str(RAIZ / "respuestas_gpu" / "respuestas_nube.json"))
    args = p.parse_args()

    clave = os.environ.get("ANTHROPIC_API_KEY")
    if not clave:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")

    datos = json.loads(Path(args.entrada).read_text(encoding="utf-8"))
    casos = next(iter(datos.values()))
    print(f"{len(casos)} preguntas, con los mismos fragmentos que recibió el modelo propio")

    import anthropic

    from index.costos import liquidar

    cliente = anthropic.Anthropic(api_key=clave)
    gasto = 0.0
    salida = []
    for i, caso in enumerate(casos, 1):
        fragmentos = _formatear_fragmentos(caso.get("fragmentos", []))
        mensaje = f"{fragmentos}\n\nPregunta: {caso['pregunta']}"
        r = cliente.messages.create(
            model=args.modelo,
            max_tokens=600,
            system=PROMPT_SISTEMA,
            messages=[{"role": "user", "content": mensaje}],
        )
        gasto += liquidar(r.usage, args.modelo).usd
        texto = "".join(b.text for b in r.content if hasattr(b, "text")).strip()
        salida.append({**caso, "respuesta_modelo": texto})
        if i % 25 == 0:
            print(f"  {i}/{len(casos)} — {gasto:.3f} USD")

    ruta = Path(args.salida)
    ruta.write_text(json.dumps({args.modelo: salida}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nCosto real de generar: {gasto:.2f} USD ({args.modelo})")
    print(f"{len(salida)} respuestas en {ruta}")
    print("Ahora júzgalas con el MISMO juez que las del modelo propio:")
    print(f"  ./venv/Scripts/python.exe finetune/juzgar_respuestas.py {ruta}")


if __name__ == "__main__":
    main()
