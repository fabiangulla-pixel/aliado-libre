"""Corrige el desajuste real encontrado al evaluar los modelos: el dataset de
entrenamiento anterior (finetune/generar_dataset_ampliado.py) le mostraba al
modelo UN solo fragmento por ejemplo, pero en producción (index/responder.py,
vía IndiceBusqueda.buscar) siempre recibe 5 a la vez — el modelo nunca
aprendió a elegir cuál de varios fragmentos citar, y por eso en la evaluación
de 150 preguntas confundía fragmentos irrelevantes con el correcto en vez de
decir "no sé".

Este script genera un dataset donde cada ejemplo usa los 5 fragmentos REALES
que trae IndiceBusqueda.buscar() para esa pregunta — exactamente lo que el
modelo va a ver en producción:

- Positivos: se genera una pregunta a partir de un fragmento real, se corre
  la búsqueda real sobre esa pregunta, y SOLO se conserva el ejemplo si el
  fragmento de origen aparece entre los 5 resultados (si no aparece, es un
  fallo de recuperación, no algo que el modelo deba aprender a resolver —
  se descarta y se cuenta, es señal útil sobre el buscador).
- Negativos: se corre la búsqueda real sobre una pregunta ajena y se
  excluye cualquier resultado que coincida con el documento de origen de esa
  pregunta, dejando los 5 fragmentos irrelevantes que sí traería el buscador
  en un caso real de "no tengo esto indexado".

Requiere ANTHROPIC_API_KEY en el entorno.

Uso:
    ./venv/Scripts/python.exe finetune/generar_dataset_multifragmento.py [n_positivos] [n_negativos]
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finetune.generar_dataset_ampliado import _generar_pregunta_respuesta, _muestrear_fragmentos
from index.buscar import IndiceBusqueda
from index.responder import PROMPT_SISTEMA, _formatear_fragmentos

RAIZ = Path(__file__).resolve().parent
RESPUESTA_NO_SE = "No encontré información suficiente en el índice para responder esto con certeza."
PRECIO_ENTRADA_POR_M = 1.0
PRECIO_SALIDA_POR_M = 5.0
MODELO_GENERADOR = "claude-haiku-4-5"


def _construir_ejemplo(pregunta: str, resultados: list[dict], respuesta: str) -> dict:
    contexto = _formatear_fragmentos(resultados)
    prompt = (
        f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}\n\nPregunta: {pregunta}\n\nRespuesta:"
    )
    return {"prompt": prompt, "completion": " " + respuesta}


def main() -> None:
    import anthropic

    n_positivos = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    n_negativos = int(sys.argv[2]) if len(sys.argv) > 2 else 35

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")
    cliente = anthropic.Anthropic(api_key=api_key)

    print("Cargando índice de búsqueda real (una sola vez, ~1-2 min)...")
    indice = IndiceBusqueda()

    print(f"Muestreando {int(n_positivos * 1.4) + n_negativos + 10} fragmentos candidatos...")
    fragmentos = _muestrear_fragmentos(int(n_positivos * 1.4) + n_negativos + 10, semilla=9001)
    rng = random.Random(13)
    rng.shuffle(fragmentos)

    tokens_in_total = 0
    tokens_out_total = 0
    ejemplos = []
    preguntas_generadas: list[tuple[dict, str]] = []
    fallos_recuperacion = 0

    print(f"Generando hasta {n_positivos} ejemplos positivos (con recuperación real, 5 fragmentos)...")
    idx = 0
    while len([e for e in ejemplos if not e.get("_neg")]) < n_positivos and idx < len(fragmentos):
        frag = fragmentos[idx]
        idx += 1
        resultado = _generar_pregunta_respuesta(cliente, frag)
        if resultado is None:
            continue
        pregunta, respuesta, t_in, t_out = resultado
        tokens_in_total += t_in
        tokens_out_total += t_out

        resultados_reales = indice.buscar(pregunta, k=5)
        ids_encontrados = {r.get("identificador_documento") for r in resultados_reales}
        if frag["identificador_documento"] not in ids_encontrados:
            fallos_recuperacion += 1
            continue  # el buscador real no trajo el fragmento de origen: no es un caso entrenable

        preguntas_generadas.append((frag, pregunta))
        ej = _construir_ejemplo(pregunta, resultados_reales, respuesta)
        ej["_neg"] = False
        ejemplos.append(ej)
        n_hechos = len([e for e in ejemplos if not e.get("_neg")])
        if n_hechos % 20 == 0:
            print(
                f"  {n_hechos}/{n_positivos} positivos (recuperación real) | {fallos_recuperacion} descartados por fallo de recuperación"
            )

    print(
        f"Positivos generados: {len([e for e in ejemplos if not e.get('_neg')])} | descartados por fallo de recuperación: {fallos_recuperacion}"
    )

    print(f"Generando {n_negativos} ejemplos negativos (5 fragmentos reales, ninguno relevante)...")
    vistas: set[str] = set()
    pool_negativo = []
    for f, p in preguntas_generadas:
        clave = p.strip().lower()[:60]
        if clave in vistas:
            continue
        vistas.add(clave)
        pool_negativo.append((f, p))
    rng.shuffle(pool_negativo)

    n_neg_hechos = 0
    for frag_origen, pregunta in pool_negativo:
        if n_neg_hechos >= n_negativos:
            break
        resultados_reales = indice.buscar(pregunta, k=8)
        filtrados = [
            r
            for r in resultados_reales
            if r.get("identificador_documento") != frag_origen["identificador_documento"]
        ][:5]
        if len(filtrados) < 3:
            continue  # sin suficientes fragmentos distractores reales, se salta
        ej = _construir_ejemplo(pregunta, filtrados, RESPUESTA_NO_SE)
        ej["_neg"] = True
        ejemplos.append(ej)
        n_neg_hechos += 1

    print(f"Negativos generados: {n_neg_hechos}")

    for ej in ejemplos:
        ej.pop("_neg", None)
    rng.shuffle(ejemplos)

    salida = RAIZ / "data" / "entrenamiento.jsonl"
    with salida.open("w", encoding="utf-8") as f:
        for ej in ejemplos:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")

    costo = (
        tokens_in_total / 1_000_000 * PRECIO_ENTRADA_POR_M
        + tokens_out_total / 1_000_000 * PRECIO_SALIDA_POR_M
    )
    print(f"\n{len(ejemplos)} ejemplos escritos en {salida}")
    print(
        f"Costo real: {tokens_in_total} tokens entrada + {tokens_out_total} tokens salida ~= US${costo:.4f} ({MODELO_GENERADOR})"
    )
    print(
        f"Tasa de recuperación real del buscador para preguntas nuevas: {len(preguntas_generadas)}/{len(preguntas_generadas) + fallos_recuperacion} generadas trajeron su propio fragmento en el top-5."
    )


if __name__ == "__main__":
    main()
