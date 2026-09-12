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
# arregla. Ver docs/PROJECT_STATE.md.
CANDIDATOS = int(os.environ.get("ALIADO_RERANKER_CANDIDATOS", "40"))
MAX_LONGITUD = 512

_modelo = None
_candado = threading.Lock()
_fallo: str | None = None
_gpu: bool | None = None
# Se aceptan las mismas formas que en el resto del programa, en español incluido.
VERDADEROS = {"1", "true", "si", "sí"}


def _hay_gpu() -> bool:
    """True si torch ve una GPU. Se memoriza: importar torch no es gratis."""
    global _gpu
    if _gpu is None:
        try:
            import torch

            _gpu = bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001 - sin torch no hay reranker que encender
            _gpu = False
    return _gpu


def _opciones_dtype() -> dict:
    """En GPU carga el modelo en media precisión. Es 2,9x más rápido y ordena igual.

    Medido sobre las 60 primeras consultas del banco apartado, con sus candidatos
    reales: 3,49 s por consulta en float32 contra 1,19 s en float16. Lo que
    autoriza el cambio no es la velocidad sino el acuerdo: **60 de 60 con el
    mismo top-1, el mismo top-5 y en el mismo orden**, y el ancla dentro del
    top-5 en los mismos 16 casos. O sea que los +10 puntos de recall@5 medidos
    en float32 se heredan enteros; no es una aproximación que haya que volver a
    validar.

    Solo en GPU: en CPU la media precisión no está acelerada y sale más lenta.
    """
    if not _hay_gpu():
        return {}
    try:
        import torch

        return {"model_kwargs": {"torch_dtype": torch.float16}}
    except Exception:  # noqa: BLE001 - sin torch no se llega hasta aquí
        return {}


def cargar_reranker():
    """Carga perezosa y una sola vez; el modelo pesa y el servidor es multihilo."""
    global _modelo, _fallo
    if _modelo is not None or _fallo is not None:
        return _modelo
    with _candado:
        if _modelo is None and _fallo is None:
            try:
                from sentence_transformers import CrossEncoder

                _modelo = CrossEncoder(MODELO_RERANKER, max_length=MAX_LONGITUD, **_opciones_dtype())
            except Exception as e:  # noqa: BLE001 - sin reranker se sigue buscando
                _fallo = f"{type(e).__name__}: {e}"
    return _modelo


def disponible() -> bool:
    return cargar_reranker() is not None


def activo() -> bool:
    """Decide si reordenar. **Apagado por defecto desde el 12-sep-2026.**

    Se adoptó por +10 puntos de recall@5 (33,5% -> 43,5%) medidos el 7-sep-2026.
    Esa medición se hizo sobre un banco cuyas consultas se habían redactado A
    PARTIR del fragmento que debían recuperar, así que compartían su vocabulario.
    Con consultas escritas como las escribe la gente, **empeora**:

        sin reordenar   27%      (44 consultas del conjunto de desarrollo)
        ventana 40      23%
        ventana 120     20%

    Y hay un caso real que lo enseña mejor que la tabla. Ante «puedo tener mi
    herencia antes de que mueran mis padres», la fusión devuelve primero la
    LEY-84-1873 —el Código Civil, que es donde está la respuesta— con puntaje
    0,0284. El reordenador la saca del top-5 y pone en su lugar el DECRETO-475-1938,
    sobre la Caja de Auxilios de la Policía Nacional. Le quitó al usuario la
    respuesta correcta y le dejó un decreto de 1938.

    No se borra el código: sigue siendo la herramienta adecuada para un problema
    de ordenamiento, y el diagnóstico dice que hay margen (el documento correcto
    está entre los 120 candidatos el 69% de las veces y solo llega al top-5 el
    29%). Lo que está medido es que ESTE reordenador, con ESTE corpus y consultas
    en lenguaje llano, no cobra ese margen sino que lo destruye.

    `ALIADO_RERANKER_ACTIVO=1` lo enciende para quien quiera volver a medirlo.
    """
    crudo = os.environ.get("ALIADO_RERANKER_ACTIVO", "").strip().lower()
    if crudo:
        return crudo in VERDADEROS
    return False


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
        # Un solo lote: son 40 pares y el batch por defecto (32) los parte en dos
        # sin ganar nada, ni en memoria ni en tiempo.
        puntajes = modelo.predict(pares, batch_size=max(len(pares), 1))
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
    print("hay gpu:", _hay_gpu())
    print("activo por defecto:", activo())
    print("disponible:", disponible())
    if not disponible():
        print("motivo:", _fallo)
