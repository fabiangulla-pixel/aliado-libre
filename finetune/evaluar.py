"""Evalúa los dos modelos fine-tuneados (0.5B vs 1.5B) sobre un banco de
preguntas de prueba nuevas (no vistas en entrenamiento), usando el pipeline
de producción real (IndiceBusqueda.buscar + PROMPT_SISTEMA), y un juez
(Claude) que compara cada respuesta contra los fragmentos reales que recibió
el modelo — no contra una "respuesta ideal" fija, para poder juzgar también
si citó la fuente correcta entre varias disponibles.

Genera el banco de prueba igual que finetune/generar_dataset_ampliado.py pero
con semilla distinta (no debe solaparse con el set de entrenamiento), y sin
guardarlo como material de entrenamiento.

Requiere ANTHROPIC_API_KEY en el entorno.

Uso:
    ./venv/Scripts/python.exe finetune/evaluar.py
    ./venv/Scripts/python.exe finetune/evaluar.py --n 15 --negativos 4
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finetune.generar_dataset_ampliado import (
    PROMPT_GENERAR_POSITIVO,
    _muestrear_fragmentos,
)
from index.buscar import IndiceBusqueda
from index.responder import PROMPT_SISTEMA, _formatear_fragmentos

RAIZ = Path(__file__).resolve().parent
RESPUESTA_NO_SE = "No encontré información suficiente en el índice para responder esto con certeza."
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


def _generar_banco_prueba(cliente, n_positivos: int, n_negativos: int, semilla: int) -> list[dict]:
    fragmentos = _muestrear_fragmentos(n_positivos + n_negativos + 10, semilla=semilla)
    rng = random.Random(semilla + 1)
    rng.shuffle(fragmentos)
    frags_pos = fragmentos[:n_positivos]
    frags_neg = fragmentos[n_positivos : n_positivos + n_negativos]

    banco = []
    preguntas_pos = []
    for frag in frags_pos:
        prompt = PROMPT_GENERAR_POSITIVO.format(
            fuente=frag["fuente"],
            identificador=frag["identificador_documento"] or frag["fuente"],
            texto=frag["texto"],
        )
        r = cliente.messages.create(
            model=MODELO_JUEZ, max_tokens=500, messages=[{"role": "user", "content": prompt}]
        )
        texto = "".join(b.text for b in r.content if hasattr(b, "text")).strip()
        m = re.search(r"\{.*\}", texto, re.DOTALL)
        if not m:
            continue
        try:
            datos = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        pregunta, respuesta = datos["pregunta"].strip(), datos["respuesta"].strip()
        preguntas_pos.append(pregunta)
        banco.append({"pregunta": pregunta, "respuesta_esperada": respuesta, "es_negativo": False})

    for i, _frag in enumerate(frags_neg):
        # pregunta tomada de un positivo de fuente distinta, ya generada arriba
        pregunta_ajena = preguntas_pos[(i + 3) % len(preguntas_pos)] if preguntas_pos else None
        if pregunta_ajena is None:
            continue
        banco.append({"pregunta": pregunta_ajena, "respuesta_esperada": RESPUESTA_NO_SE, "es_negativo": True})

    rng.shuffle(banco)
    return banco


def _responder_con_gguf(modelo, indice: IndiceBusqueda, pregunta: str) -> tuple[str, list[dict]]:
    resultados = indice.buscar(pregunta, k=5)
    if not resultados:
        return RESPUESTA_NO_SE, []
    contexto = _formatear_fragmentos(resultados)
    prompt = (
        f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}\n\nPregunta: {pregunta}\n\nRespuesta:"
    )
    salida = modelo(prompt, max_tokens=400, temperature=0.2, stop=["Pregunta:", "###"])
    return salida["choices"][0]["text"].strip(), resultados


def _juzgar(
    cliente, pregunta: str, resultados: list[dict], respuesta_esperada: str, respuesta_modelo: str
) -> dict:
    fragmentos_texto = _formatear_fragmentos(resultados) if resultados else "(sin fragmentos)"
    prompt = PROMPT_JUEZ.format(
        pregunta=pregunta,
        fragmentos=fragmentos_texto,
        respuesta_esperada=respuesta_esperada,
        respuesta_modelo=respuesta_modelo,
    )
    r = cliente.messages.create(
        model=MODELO_JUEZ, max_tokens=300, messages=[{"role": "user", "content": prompt}]
    )
    texto = "".join(b.text for b in r.content if hasattr(b, "text")).strip()
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        return {"correcto": False, "razon": "el juez no devolvió JSON válido"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"correcto": False, "razon": "el juez no devolvió JSON válido"}


def main() -> None:
    import anthropic
    from llama_cpp import Llama

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=15, help="preguntas totales por modelo")
    parser.add_argument("--negativos", type=int, default=4, help="cuántas de esas son casos de 'no sé'")
    parser.add_argument(
        "--semilla", type=int, default=2024, help="distinta de la usada en el dataset de entrenamiento"
    )
    args = parser.parse_args()
    n_positivos = args.n - args.negativos

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")
    cliente = anthropic.Anthropic(api_key=api_key)

    print(
        f"Generando banco de prueba ({n_positivos} positivas + {args.negativos} negativas, semilla={args.semilla})..."
    )
    banco = _generar_banco_prueba(cliente, n_positivos, args.negativos, args.semilla)
    print(f"{len(banco)} preguntas de prueba generadas.\n")

    (RAIZ / "eval").mkdir(exist_ok=True)
    (RAIZ / "eval" / "banco_prueba.json").write_text(
        json.dumps(banco, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Cargando índice de búsqueda (una sola vez para ambos modelos)...")
    indice = IndiceBusqueda()

    # Autodetecta cualquier .gguf en finetune/salida/ en vez de una lista fija con
    # nombres hardcodeados — así corre igual sobre los modelos Qwen2.5 viejos o
    # los Qwen3.5 nuevos sin tener que editar este script cada vez.
    modelos = {ruta.stem: ruta for ruta in sorted((RAIZ / "salida").glob("*.gguf"))}
    if not modelos:
        raise SystemExit(f"No hay ningún .gguf en {RAIZ / 'salida'} — exporta un modelo primero.")

    archivo_resultados = RAIZ / "eval" / "resultados.json"
    resultados_finales = {}
    for nombre, ruta in modelos.items():
        print(f"\n=== Evaluando {nombre} ({ruta.name}) ===")
        # 4096 se quedaba corto con 5 fragmentos largos + pregunta + max_tokens de
        # respuesta (crash real visto: "Requested tokens (4372) exceed context
        # window of 4096" a mitad de una corrida de 150 preguntas).
        modelo = Llama(model_path=str(ruta), n_ctx=8192, verbose=False)

        aciertos = 0
        detalle = []
        for i, caso in enumerate(banco, 1):
            try:
                respuesta, resultados = _responder_con_gguf(modelo, indice, caso["pregunta"])
            except ValueError as e:
                print(f"  [{i}/{len(banco)}] ERROR generando respuesta ({e}), se cuenta como fallo")
                detalle.append(
                    {
                        "pregunta": caso["pregunta"],
                        "es_negativo": caso["es_negativo"],
                        "respuesta_modelo": f"(error: {e})",
                        "correcto": False,
                        "razon": "excepción al generar la respuesta, no se pudo evaluar",
                    }
                )
                continue
            juicio = _juzgar(cliente, caso["pregunta"], resultados, caso["respuesta_esperada"], respuesta)
            correcto = bool(juicio.get("correcto"))
            aciertos += correcto
            marca = "OK" if correcto else "FAIL"
            print(f"  [{i}/{len(banco)}] {marca} - {caso['pregunta'][:70]}")
            detalle.append(
                {
                    "pregunta": caso["pregunta"],
                    "es_negativo": caso["es_negativo"],
                    "respuesta_modelo": respuesta,
                    "correcto": correcto,
                    "razon": juicio.get("razon", ""),
                }
            )
            time.sleep(0.3)  # no saturar la API del juez

            # checkpoint incremental: si algo falla a mitad de una corrida larga
            # (cientos de preguntas x varios modelos), no se pierde todo el progreso
            precision_parcial = aciertos / i * 100
            resultados_finales[nombre] = {
                "aciertos": aciertos,
                "total": i,
                "precision_pct": precision_parcial,
                "en_progreso": i < len(banco),
                "detalle": detalle,
            }
            archivo_resultados.write_text(
                json.dumps(resultados_finales, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        precision = aciertos / len(banco) * 100 if banco else 0.0
        print(f"{nombre}: {aciertos}/{len(banco)} correctas ({precision:.0f}%)")
        resultados_finales[nombre]["en_progreso"] = False
        archivo_resultados.write_text(
            json.dumps(resultados_finales, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        del modelo  # libera RAM antes de cargar el siguiente modelo

    (RAIZ / "eval" / "resultados.json").write_text(
        json.dumps(resultados_finales, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 50)
    print("RESUMEN")
    for nombre, r in resultados_finales.items():
        print(f"  {nombre}: {r['aciertos']}/{r['total']} ({r['precision_pct']:.0f}%)")
    print(f"\nDetalle completo en {RAIZ / 'eval' / 'resultados.json'}")


if __name__ == "__main__":
    main()
