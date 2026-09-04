"""Genera un dataset de entrenamiento más grande y sin sesgo de tema que el
original (finetune/generar_dataset.py, 50 ejemplos hechos a mano sobre solo
41 fragmentos, con 3/10 negativos concentrados en "fiducia mercantil" — eso
le enseñó al modelo 0.5B a asociar ese tema con "no sé" sin importar el
fragmento real, en vez de aprender el patrón general).

Estrategia:
1. Muestrea fragmentos NUEVOS y diversos directo del Chroma real (no de
   muestra_filtrada.json, que ya está agotado), estratificado por fuente.
2. Por cada fragmento positivo, le pide a Claude Haiku que redacte una
   pregunta específica y su respuesta ideal (mismo estilo que los ejemplos
   humanos: "Según <fuente> (art. X), ..."), ANCLADA solo en ese fragmento.
3. Para negativos, empareja un fragmento con una pregunta generada a partir
   de OTRO fragmento de tema distinto — barajado para que ningún tema se
   repita en más de un ejemplo negativo (la causa raíz del sesgo anterior).

Requiere ANTHROPIC_API_KEY en el entorno (no se guarda en el proyecto).

Uso:
    ./venv/Scripts/python.exe finetune/generar_dataset_ampliado.py [n_positivos] [n_negativos]
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from index.responder import PROMPT_SISTEMA, _formatear_fragmentos

RAIZ = Path(__file__).resolve().parent
DIR_INDICE = RAIZ.parent / "index" / "chroma_db"
COLECCION = "aliado_libre"
RESPUESTA_NO_SE = "No encontré información suficiente en el índice para responder esto con certeza."

MODELO_GENERADOR = "claude-haiku-4-5"

PROMPT_GENERAR_POSITIVO = """Este es un fragmento real de una norma/sentencia/concepto jurídico colombiano:

Fuente: {fuente}
Identificador: {identificador}
Texto:
{texto}

Redacta UNA pregunta específica y factual que este fragmento responda directamente, y su respuesta ideal.
La respuesta debe:
- Empezar con "Según {identificador}" (o el nombre más natural de la norma/sentencia si el identificador es un código).
- Citar el artículo o número exacto si el fragmento lo trae.
- Ser fiel solo a lo que dice el fragmento, sin agregar nada que no esté ahí.
- Tener 2-4 frases.

Responde SOLO con JSON válido, sin texto adicional: {{"pregunta": "...", "respuesta": "..."}}"""


def _fragmento_como_resultado(doc_id: str, texto: str, meta: dict) -> dict:
    return {
        "titulo_documento": meta.get("titulo_documento") or meta.get("identificador_documento"),
        "fuente": meta.get("fuente"),
        "identificador_documento": meta.get("identificador_documento"),
        "texto": texto,
    }


def _muestrear_fragmentos(n: int, semilla: int = 42) -> list[dict]:
    import chromadb

    cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
    coleccion = cliente.get_or_create_collection(COLECCION)
    total = coleccion.count()
    if total == 0:
        raise SystemExit("El índice está vacío — no hay de dónde muestrear fragmentos.")

    rng = random.Random(semilla)
    candidatos: list[dict] = []
    intentos = 0
    vistos: set[str] = set()
    # sobre-muestrea offsets al azar y filtra por longitud razonable
    # (ni fragmentos truncados sin contexto, ni bloques enormes que no caben en el prompt)
    while len(candidatos) < n and intentos < n * 15:
        intentos += 1
        offset = rng.randint(0, total - 1)
        lote = coleccion.get(include=["documents", "metadatas"], limit=1, offset=offset)
        if not lote["ids"]:
            continue
        doc_id = lote["ids"][0]
        if doc_id in vistos:
            continue
        vistos.add(doc_id)
        texto = lote["documents"][0]
        meta = lote["metadatas"][0]
        if not (300 <= len(texto) <= 1800):
            continue
        candidatos.append(_fragmento_como_resultado(doc_id, texto, meta))

    return candidatos


def _generar_pregunta_respuesta(cliente, fragmento: dict) -> tuple[str, str, int, int] | None:
    prompt = PROMPT_GENERAR_POSITIVO.format(
        fuente=fragmento["fuente"],
        identificador=fragmento["identificador_documento"] or fragmento["fuente"],
        texto=fragmento["texto"],
    )
    respuesta = cliente.messages.create(
        model=MODELO_GENERADOR,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    tokens_in = respuesta.usage.input_tokens
    tokens_out = respuesta.usage.output_tokens
    texto = "".join(b.text for b in respuesta.content if hasattr(b, "text")).strip()
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if not match:
        return None
    try:
        datos = json.loads(match.group(0))
        return datos["pregunta"].strip(), datos["respuesta"].strip(), tokens_in, tokens_out
    except (json.JSONDecodeError, KeyError):
        return None


# USD por millón de tokens, Claude Haiku 4.5 (input/output) — ajustar si cambia el pricing.
PRECIO_ENTRADA_POR_M = 1.0
PRECIO_SALIDA_POR_M = 5.0


def _construir_ejemplo(pregunta: str, resultados: list[dict], respuesta: str) -> dict:
    contexto = _formatear_fragmentos(resultados)
    prompt = (
        f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}\n\nPregunta: {pregunta}\n\nRespuesta:"
    )
    return {"prompt": prompt, "completion": " " + respuesta}


def main() -> None:
    import anthropic

    n_positivos = int(sys.argv[1]) if len(sys.argv) > 1 else 140
    n_negativos = int(sys.argv[2]) if len(sys.argv) > 2 else 35

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")
    cliente = anthropic.Anthropic(api_key=api_key)

    print(f"Muestreando {n_positivos + n_negativos + 10} fragmentos diversos del índice real...")
    fragmentos = _muestrear_fragmentos(n_positivos + n_negativos + 10)
    print(f"{len(fragmentos)} fragmentos únicos obtenidos.")
    if len(fragmentos) < n_positivos + n_negativos:
        raise SystemExit("No se muestrearon suficientes fragmentos válidos, baja n_positivos/n_negativos.")

    rng = random.Random(7)
    rng.shuffle(fragmentos)
    fragmentos_positivos = fragmentos[:n_positivos]
    fragmentos_negativos_base = fragmentos[n_positivos : n_positivos + n_negativos]

    ejemplos = []
    tokens_entrada_total = 0
    tokens_salida_total = 0

    print(f"Generando {len(fragmentos_positivos)} ejemplos positivos con {MODELO_GENERADOR}...")
    preguntas_generadas: list[tuple[dict, str]] = []
    for i, frag in enumerate(fragmentos_positivos, 1):
        resultado = _generar_pregunta_respuesta(cliente, frag)
        if resultado is None:
            print(f"  [{i}] fallo al parsear respuesta, se omite")
            continue
        pregunta, respuesta, tokens_in, tokens_out = resultado
        tokens_entrada_total += tokens_in
        tokens_salida_total += tokens_out
        preguntas_generadas.append((frag, pregunta))
        ejemplos.append(_construir_ejemplo(pregunta, [frag], respuesta))
        if i % 20 == 0:
            print(f"  [{i}/{len(fragmentos_positivos)}]")

    print(
        f"Generando {len(fragmentos_negativos_base)} ejemplos negativos (fragmento + pregunta de OTRO tema)..."
    )
    # Empareja cada fragmento negativo con una pregunta de un fragmento POSITIVO
    # distinto y de tema distinto — así ningún tema se repite del lado "no sé",
    # a diferencia del dataset original donde "fiducia mercantil" apareció 3 veces
    # solo como negativo y nunca como positivo.
    # Dedupe por texto de pregunta (documentos vecinos del mismo caso, ej. autos de
    # conflicto de jurisdicción de la Corte Constitucional, generan preguntas casi
    # idénticas) — sin esto, la misma pregunta puede terminar asignada a dos
    # negativos distintos, o reforzar un solo tema como "siempre no sé".
    vistas: set[str] = set()
    preguntas_disponibles = []
    for f, p in preguntas_generadas:
        clave = p.strip().lower()[:60]
        if clave in vistas:
            continue
        vistas.add(clave)
        preguntas_disponibles.append((f, p))
    rng.shuffle(preguntas_disponibles)

    for _i, frag_negativo in enumerate(fragmentos_negativos_base):
        if not preguntas_disponibles:
            break
        # toma y CONSUME una pregunta cuyo fragmento de origen sea de fuente
        # distinta (o cualquiera si no hay, agotando el pool sin reponerlo, para
        # que ninguna pregunta se reutilice en dos negativos distintos)
        idx = next(
            (j for j, (f, _) in enumerate(preguntas_disponibles) if f["fuente"] != frag_negativo["fuente"]),
            0,
        )
        _, candidata = preguntas_disponibles.pop(idx)
        ejemplos.append(_construir_ejemplo(candidata, [frag_negativo], RESPUESTA_NO_SE))

    rng.shuffle(ejemplos)
    salida = RAIZ / "data" / "entrenamiento.jsonl"
    with salida.open("w", encoding="utf-8") as f:
        for ej in ejemplos:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")

    costo = (
        tokens_entrada_total / 1_000_000 * PRECIO_ENTRADA_POR_M
        + tokens_salida_total / 1_000_000 * PRECIO_SALIDA_POR_M
    )
    print(f"\n{len(ejemplos)} ejemplos escritos en {salida}")
    print(
        f"Costo real: {tokens_entrada_total} tokens entrada + {tokens_salida_total} tokens salida "
        f"~= US${costo:.4f} ({MODELO_GENERADOR})"
    )


if __name__ == "__main__":
    main()
