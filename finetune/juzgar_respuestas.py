"""Juzga respuestas YA generadas (por ejemplo, con GPU en Colab vía
finetune/colab_evaluar_gpu.ipynb, descargadas a finetune/respuestas_gpu/respuestas_gpu.json)
contra los fragmentos reales que recibió cada modelo — no genera nada nuevo,
solo llama al juez (Claude), así que es rápido sin importar cuánto tarden en
generarse las respuestas.

Uso:
    ./venv/Scripts/python.exe finetune/juzgar_respuestas.py [ruta_respuestas.json]
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from index.costos import liquidar
from index.responder import _formatear_fragmentos

RAIZ = Path(__file__).resolve().parent
MODELO_JUEZ = "claude-haiku-4-5"

PROMPT_JUEZ = """Eres un evaluador estricto de un asistente legal RAG (recuperación + generación).

Pregunta del usuario: {pregunta}

Fragmentos que el asistente tenía disponibles para responder:
{fragmentos}

Respuesta esperada (referencia, generada aparte, puede no ser la única forma correcta): {respuesta_esperada}

Respuesta que dio el modelo evaluado: {respuesta_modelo}

Evalúa la respuesta del modelo con estos criterios:
1. ¿Es fiel a los fragmentos (no inventa nada que no esté en ellos)?
2. ¿Cita la fuente/identificador correcto (el que realmente contiene la información, no otro fragmento
   presente pero irrelevante)?
3. Si la pregunta NO tiene respuesta en los fragmentos, ¿el modelo lo reconoció en vez de inventar?

Responde SOLO con JSON: {{"correcto": true/false, "razon": "una frase explicando por qué"}}"""


def _juzgar(
    cliente, pregunta: str, fragmentos: list[dict], respuesta_esperada: str, respuesta_modelo: str
) -> tuple[dict, object]:
    fragmentos_texto = _formatear_fragmentos(fragmentos) if fragmentos else "(sin fragmentos)"
    prompt = PROMPT_JUEZ.format(
        pregunta=pregunta,
        fragmentos=fragmentos_texto,
        respuesta_esperada=respuesta_esperada,
        respuesta_modelo=respuesta_modelo,
    )
    import re

    r = cliente.messages.create(
        model=MODELO_JUEZ, max_tokens=300, messages=[{"role": "user", "content": prompt}]
    )
    texto = "".join(b.text for b in r.content if hasattr(b, "text")).strip()
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    fallo = {"correcto": False, "razon": "el juez no devolvió JSON válido"}
    if not m:
        return fallo, r.usage
    try:
        return json.loads(m.group(0)), r.usage
    except json.JSONDecodeError:
        return fallo, r.usage


def main() -> None:
    import anthropic

    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "respuestas_gpu" / "respuestas_gpu.json"
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")
    cliente = anthropic.Anthropic(api_key=api_key)

    datos = json.loads(ruta.read_text(encoding="utf-8"))
    gasto_usd = 0.0
    archivo_resultados = RAIZ / "eval" / "resultados.json"
    resultados_finales = {}

    for nombre, respuestas in datos.items():
        print(f"\n=== Juzgando {nombre} ({len(respuestas)} respuestas) ===")
        aciertos = 0
        detalle = []
        for i, caso in enumerate(respuestas, 1):
            juicio, uso = _juzgar(
                cliente,
                caso["pregunta"],
                caso.get("fragmentos", []),
                caso["respuesta_esperada"],
                caso["respuesta_modelo"],
            )
            gasto_usd += liquidar(uso, MODELO_JUEZ).usd
            correcto = bool(juicio.get("correcto"))
            aciertos += correcto
            marca = "OK" if correcto else "FAIL"
            print(f"  [{i}/{len(respuestas)}] {marca} - {caso['pregunta'][:70]}  [{gasto_usd:.3f} USD]")
            detalle.append(
                {
                    "pregunta": caso["pregunta"],
                    "es_negativo": caso["es_negativo"],
                    "respuesta_modelo": caso["respuesta_modelo"],
                    "correcto": correcto,
                    "razon": juicio.get("razon", ""),
                }
            )
            time.sleep(0.3)

            precision_parcial = aciertos / i * 100
            resultados_finales[nombre] = {
                "aciertos": aciertos,
                "total": i,
                "precision_pct": precision_parcial,
                "en_progreso": i < len(respuestas),
                "detalle": detalle,
            }
            archivo_resultados.write_text(
                json.dumps(resultados_finales, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        precision = aciertos / len(respuestas) * 100 if respuestas else 0.0
        print(f"{nombre}: {aciertos}/{len(respuestas)} correctas ({precision:.0f}%)")

    print("\n" + "=" * 50)
    print("RESUMEN")
    for nombre, r in resultados_finales.items():
        print(f"  {nombre}: {r['aciertos']}/{r['total']} ({r['precision_pct']:.0f}%)")
    print(f"\nDetalle completo en {archivo_resultados}")


if __name__ == "__main__":
    main()
