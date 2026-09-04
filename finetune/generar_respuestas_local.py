"""Genera las respuestas de un modelo GGUF sobre el banco de 150 preguntas,
en CPU local, con los MISMOS parámetros de inferencia que usó la evaluación
en GPU (finetune/colab_evaluar_gpu.ipynb) — misma temperatura, mismo
max_tokens, mismos stops y el mismo n_ctx — para que el número resultante sea
comparable contra los 4 modelos ya evaluados y no una medición nueva.

Reusa los prompts ya precalculados (finetune/eval/prompts_precalculados.json),
así que NO carga el índice de 9GB.

Guarda progreso tras cada respuesta: una corrida de 150 inferencias en CPU
tarda horas y no puede perderse por un corte. Si el archivo de salida ya
tiene respuestas para este modelo, reanuda donde quedó.

Uso:
    ./venv/Scripts/python.exe finetune/generar_respuestas_local.py finetune/salida/modelo_lora_15b.q4_k_m.gguf
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Mismos valores que colab_evaluar_gpu.ipynb: cambiarlos rompe la comparabilidad
# con los resultados de los 4 modelos ya medidos.
N_CTX = 8192
MAX_TOKENS = 400
TEMPERATURA = 0.2
STOPS = ["Pregunta:", "###"]


def _cargar(ruta: Path) -> dict:
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ruta_gguf", help="ruta al .gguf a evaluar")
    parser.add_argument(
        "--salida",
        default=str(RAIZ / "respuestas_gpu" / "respuestas_local.json"),
        help="archivo JSON de respuestas (mismo formato que espera juzgar_respuestas.py)",
    )
    parser.add_argument("--limite", type=int, default=0, help="evaluar solo las primeras N preguntas")
    args = parser.parse_args()

    ruta_gguf = Path(args.ruta_gguf)
    if not ruta_gguf.exists():
        raise SystemExit(f"No existe {ruta_gguf}")

    casos = json.loads((RAIZ / "eval" / "prompts_precalculados.json").read_text(encoding="utf-8"))
    if args.limite:
        casos = casos[: args.limite]

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    datos = _cargar(salida)
    nombre = ruta_gguf.name
    respuestas = datos.get(nombre, [])
    if respuestas:
        print(f"Reanudando: ya hay {len(respuestas)}/{len(casos)} respuestas para {nombre}.")

    from llama_cpp import Llama

    print(f"Cargando {ruta_gguf} en CPU (n_ctx={N_CTX})...")
    modelo = Llama(model_path=str(ruta_gguf), n_ctx=N_CTX, verbose=False)

    inicio = time.time()
    for i, caso in enumerate(casos, 1):
        if i <= len(respuestas):
            continue
        try:
            r = modelo(caso["prompt"], max_tokens=MAX_TOKENS, temperature=TEMPERATURA, stop=STOPS)
            texto = r["choices"][0]["text"].strip()
        except ValueError as e:  # contexto excedido u otro fallo de inferencia
            texto = f"(error: {e})"
        respuestas.append(
            {
                "pregunta": caso["pregunta"],
                "respuesta_esperada": caso["respuesta_esperada"],
                "es_negativo": caso["es_negativo"],
                "fragmentos": caso["fragmentos"],
                "respuesta_modelo": texto,
            }
        )
        datos[nombre] = respuestas
        salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

        transcurrido = time.time() - inicio
        ritmo = transcurrido / max(1, i)
        restante = ritmo * (len(casos) - i) / 60
        print(f"[{i}/{len(casos)}] {transcurrido / 60:.0f} min transcurridos, ~{restante:.0f} min restantes")

    print(f"\nListo: {len(respuestas)} respuestas en {salida}")
    print(f"Ahora júzgalas con:\n  ./venv/Scripts/python.exe finetune/juzgar_respuestas.py {salida}")


if __name__ == "__main__":
    main()
