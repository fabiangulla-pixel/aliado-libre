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
from pathlib import Path

# Por defecto, bge-reranker-v2-m3 sin afinar. El DESTILADO (finetune/destilar/,
# 6-oct-2026: bge afinado con las elecciones de Sonnet como maestro) se elige con
# ALIADO_RERANKER=destilado. No es el defecto porque no está probado que gane:
# por ancla queda por debajo de bge (prueba_200: 32,0% vs 34,0% @5) y la medición
# de pertinencia, que es la que puede favorecerlo, quedó pendiente.
_DESTILADO = Path(__file__).resolve().parent.parent / "modelos" / "reranker_destilado"
_ELEGIDO = os.environ.get("ALIADO_RERANKER", "").strip()
MODELO_RERANKER = (
    str(_DESTILADO) if _ELEGIDO.lower() == "destilado" else (_ELEGIDO or "BAAI/bge-reranker-v2-m3")
)
# Fragmentos crudos que se piden a la búsqueda antes de reordenar. De ahí sale el
# pool: UN fragmento por documento, hasta DOCUMENTOS. Diversificar es lo que
# cambió el resultado: la ventana de 40 fragmentos del 12-sep traía varios del
# mismo documento y el reordenador empeoraba (27% -> 23%); con un fragmento por
# documento mejora (ver `activo`).
CANDIDATOS = int(os.environ.get("ALIADO_RERANKER_CANDIDATOS", "240"))
DOCUMENTOS = int(os.environ.get("ALIADO_RERANKER_DOCUMENTOS", "60"))
# El pasaje se presenta con su título: «ARTÍCULO 130» no dice de qué ley es.
MAX_CARACTERES = 2000
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
    """Decide si reordenar. **Encendido por defecto con GPU desde el 6-oct-2026.**

    Historia. Se adoptó el 7-sep (+10 puntos sobre un banco cuyas consultas
    compartían vocabulario con el fragmento) y se apagó el 12-sep porque con
    consultas en lenguaje llano empeoraba (27% -> 23%, ventana de 40 fragmentos):
    ante «puedo tener mi herencia antes de que mueran mis padres» sacaba el Código
    Civil del top-5 y ponía un decreto de 1938 de la Policía.

    Lo que cambió el 6-oct: el pool es de UN fragmento por documento (60
    documentos) y cada pasaje va con su título. Medido sobre los dos bancos
    apartados, misma máquina (finetune/destilar/evaluar_reordenador.py):

        banco prueba_200   hoy 24,5%  ->  bge 34,0% recall@5  (gana 24, pierde 5, p=0,0005)
        piloto 95          hoy 25,3%  ->  bge 29,5%           (gana 10, pierde 6, p=0,45)

    Solo con GPU: en CPU, 60 pares de 512 tokens tardan demasiado por consulta.
    `ALIADO_RERANKER_ACTIVO=0/1` fuerza el valor.
    """
    crudo = os.environ.get("ALIADO_RERANKER_ACTIVO", "").strip().lower()
    if crudo:
        return crudo in VERDADEROS
    return _hay_gpu()


def _pasaje(r: dict) -> str:
    titulo = r.get("titulo_documento") or ""
    texto = r.get("texto") or ""
    return (f"{titulo}\n{texto}" if titulo else texto)[:MAX_CARACTERES]


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

    candidatos = resultados[:DOCUMENTOS]
    try:
        pares = [(consulta, _pasaje(r)) for r in candidatos]
        # Un solo lote: los 60 pares caben en la GPU y partirlos no gana nada.
        puntajes = modelo.predict(pares, batch_size=max(len(pares), 1))
    except Exception:  # noqa: BLE001
        return resultados[:k] if k else resultados

    ordenados = [
        {**r, "puntaje_reranker": float(p)}
        for p, r in sorted(zip(puntajes, candidatos, strict=True), key=lambda x: -x[0])
    ]
    # los que no entraron en la ventana del reranker van detrás, en su orden
    ordenados.extend(resultados[DOCUMENTOS:])
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
