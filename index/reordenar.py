"""Reordena los candidatos recuperados leyendo pregunta y pasaje JUNTOS.

La búsqueda actual puntúa la consulta y el fragmento por separado: BM25 cuenta
palabras compartidas y el embedding compara dos vectores calculados de forma
independiente. Ninguno de los dos *lee* la pregunta frente al pasaje. Un
reranker (cross-encoder) sí: recibe el par completo y da una puntuación de
pertinencia. Es mucho más caro por candidato, y por eso se aplica solo a los
pocos que la búsqueda ya trajo.

Por qué aquí: el modo de fallo dominante medido no es inventar, es elegir mal
el pasaje de entre los que sí llegaron — citar el artículo 38 cuando la
respuesta estaba en el 39. Esa es exactamente la decisión que un reranker toma
mejor que una suma de rangos.

El modelo se descarga la primera vez (~2,2 GB para bge-reranker-v2-m3) y se
puede cambiar por variable de entorno. Si no está disponible, `reordenar`
devuelve los resultados tal cual: el buscador nunca debe caerse porque falte
una mejora opcional.
"""

from __future__ import annotations

import os
import threading

MODELO_RERANKER = os.environ.get("ALIADO_RERANKER", "BAAI/bge-reranker-v2-m3")
# Cuántos candidatos se reordenan. La intuición dice que más candidatos dan más
# margen; **medido, no es cierto**: sobre 200 consultas apartadas, las ventanas
# de 40, 100 y 200 dan el MISMO recall@5 (43,5%), y la de 200 cuesta cinco veces
# más (16,85 s/consulta en GPU frente a 3,42). El reranker ya tiene delante el
# documento correcto en los casos que falla, y no lo reconoce; darle más no lo
# arregla. Ver docs/MEDICIONES.md.
CANDIDATOS = int(os.environ.get("ALIADO_RERANKER_CANDIDATOS", "40"))
MAX_LONGITUD = 512

_modelo = None
_candado = threading.Lock()
_fallo: str | None = None


def cargar_reranker():
    """Carga perezosa y una sola vez; el modelo pesa y el servidor es multihilo."""
    global _modelo, _fallo
    if _modelo is not None or _fallo is not None:
        return _modelo
    with _candado:
        if _modelo is None and _fallo is None:
            try:
                from sentence_transformers import CrossEncoder

                _modelo = CrossEncoder(MODELO_RERANKER, max_length=MAX_LONGITUD)
            except Exception as e:  # noqa: BLE001 - sin reranker se sigue buscando
                _fallo = f"{type(e).__name__}: {e}"
    return _modelo


def disponible() -> bool:
    return cargar_reranker() is not None


def reordenar(consulta: str, resultados: list[dict], k: int | None = None) -> list[dict]:
    """Devuelve `resultados` reordenados por pertinencia real a `consulta`.

    Ante cualquier fallo devuelve el orden original: una mejora opcional no
    puede convertir una búsqueda que funciona en un error.
    """
    if not resultados or not consulta or not consulta.strip():
        return resultados[:k] if k else resultados

    modelo = cargar_reranker()
    if modelo is None:
        return resultados[:k] if k else resultados

    candidatos = resultados[:CANDIDATOS]
    try:
        pares = [(consulta, (r.get("texto") or "")[:4000]) for r in candidatos]
        puntajes = modelo.predict(pares)
    except Exception:  # noqa: BLE001
        return resultados[:k] if k else resultados

    ordenados = [
        {**r, "puntaje_reranker": float(p)}
        for p, r in sorted(zip(puntajes, candidatos, strict=True), key=lambda x: -x[0])
    ]
    # los que no entraron en la ventana del reranker van detrás, en su orden
    ordenados.extend(resultados[CANDIDATOS:])
    return ordenados[:k] if k else ordenados


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("modelo:", MODELO_RERANKER)
    print("disponible:", disponible())
    if not disponible():
        print("motivo:", _fallo)
