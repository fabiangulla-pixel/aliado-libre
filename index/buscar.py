"""Búsqueda híbrida sobre el índice: vectorial (Chroma) + léxica (SQLite
FTS5) con fusión por rango recíproco (RRF), como en ReactivosFlow. La
búsqueda léxica importa para citas exactas (números de ley, artículos) que
los embeddings por sí solos suelen perder.

Diseñado para RAM baja: ni el texto completo del corpus ni el índice léxico
viven en memoria de Python — Chroma y FTS5 son ambos disco-residentes, y solo
se trae a RAM lo estrictamente necesario para resolver cada consulta (con
718.388 fragmentos, la versión anterior con rank_bm25 en memoria medía
~10GB de RAM solo para poder arrancar; esta versión no depende del tamaño
del corpus). Esto es lo que hace viable hostear el índice en un servidor
barato en vez de necesitar un plan de ~200 USD/mes solo por RAM."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import unicodedata
from pathlib import Path

# El modelo ya queda cacheado localmente tras la primera descarga; sin esto,
# cada arranque (cada consulta MCP) golpea la red de Hugging Face solo para
# verificar que el caché sigue vigente, lo cual añade latencia innecesaria
# y puede fallar sin conexión.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import chromadb
from sentence_transformers import SentenceTransformer

# Modelo y colección se pueden cambiar por variable de entorno para poder
# comparar un índice nuevo contra el actual sin tocar código ni pisar nada.
MODELO_EMBEDDINGS = os.environ.get("ALIADO_MODELO_EMBEDDINGS", "intfloat/multilingual-e5-large")
DIR_INDICE = Path(__file__).resolve().parent / "chroma_db"
DB_FTS = Path(__file__).resolve().parent / "fts_index.db"
COLECCION = os.environ.get("ALIADO_COLECCION", "aliado_libre_multilingual_e5_large")

# Los modelos e5 se entrenaron con prefijos que distinguen la consulta del
# pasaje, y son asimétricos a propósito: sin ellos rinden bastante peor. El
# índice se construye con "passage: " (ver finetune/colab_reindexar_embeddings).
PREFIJO_CONSULTA = "query: " if "e5" in MODELO_EMBEDDINGS.lower() else ""
K_RRF = 60
# Pesos de la fusión RRF, recalibrados el 6-sep-2026 sobre el índice de
# e5-large. La calibración anterior (BM25 x2) era CORRECTA para el índice viejo
# y quedó equivocada al cambiarlo, que es la lección: un parámetro medido solo
# vale mientras valgan los supuestos bajo los que se midió.
#
# Con el embedding truncado a 128 tokens, la mitad vectorial sola acertaba el
# 10% en top-5 y había que compensarla pesando más BM25. Con el embedding nuevo,
# la vectorial sola acierta el 35,5% —más que el mejor híbrido del índice viejo—
# y ese peso la estaba estrangulando: 28,5% frente a 38,5% (p=0,0000 sobre 200
# consultas del conjunto de desarrollo).
#
# Por qué 0,8 y no 1,0, que mide algo más alto: con dos listas de candidatos casi
# disjuntas la fusión RRF deja de mezclar y se comporta como un SELECTOR de
# lista, y el cambio ocurre exactamente en 1,0 (por debajo gana la vectorial, por
# encima la léxica). Todo el rango 0,5-1,0 rinde igual dentro del ruido, así que
# se elige un valor cómodo dentro de la meseta en vez del filo del acantilado.
# Ver finetune/ajustar_pesos_rrf_v2.py.
PESO_BM25 = float(os.environ.get("ALIADO_PESO_BM25", "0.8"))
PESO_VECTORIAL = 1.0


# Palabras sin valor discriminante en español, más las fórmulas de cortesía y
# de encuadre con las que la gente envuelve una consulta ("buenas", "una
# pregunta", "gracias").
#
# No es cosmético: cada token se convierte en un término OR de FTS5, y los
# términos más frecuentes son los que tienen las listas de ocurrencias más
# largas, así que son justo los más caros. Medido sobre el banco coloquial, una
# consulta de 73 palabras tardaba 15 s solo en la parte léxica; filtrando y
# topando, 0,37 s. Media del banco: 7,82 s -> 0,39 s, veinte veces más rápido.
# Y a quien más castigaba era a quien escribe con más rodeos, es decir al
# usuario menos experto.
PALABRAS_VACIAS = frozenset(
    """a al algo alguna algunas alguno algunos ante antes aqui asi aun aunque bien buenas buenos
cada como con contra cual cuales cuando da dar de del desde dias dice decir donde dos el ella ellas
ellos en entre era eran es esa esas ese eso esos esta estan estas este esto estos estoy favor fue
fueron gracias ha hace hacer hacia han hasta hay hola la las le les lo los mas me mi mia mio mis
mucho muy nada ni no noches nos nosotros o os otra otras otro otros para pero poco por porque pregunta
puede pueden podria que quien quienes se senor senora ser seria si sin sobre solo son soy su sus
tambien tanto tardes te tener tengo tiene tienen todo todos tu tus un una uno unos usted ustedes ya
yo consulta""".split()
)

# Tope de términos por consulta. Con OR, cada término extra suma coste y
# ruido; los primeros son los que llevan la intención.
MAX_TOKENS_FTS = 12


def _sin_tildes(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _tokenizar(texto: str) -> list[str]:
    """Términos útiles de la consulta: sin palabras vacías, sin repetir y topados.

    Si al filtrar no queda nada (una consulta hecha solo de palabras vacías),
    se devuelven los tokens crudos: es preferible una búsqueda mala a ninguna.
    """
    crudos = re.findall(r"\w+", _sin_tildes(texto))
    utiles: list[str] = []
    vistos: set[str] = set()
    for token in crudos:
        if len(token) <= 2 or token in PALABRAS_VACIAS or token in vistos:
            continue
        vistos.add(token)
        utiles.append(token)
        if len(utiles) >= MAX_TOKENS_FTS:
            break
    return utiles or crudos[:MAX_TOKENS_FTS]


def _consulta_fts(tokens: list[str]) -> str:
    # cada token entre comillas dobles: evita que caracteres del texto del
    # usuario (guiones, dos puntos, asteriscos) se interpreten como sintaxis
    # especial de FTS5. OR entre tokens para recall amplio, igual que el
    # BM25 anterior no exigía que todas las palabras aparecieran.
    return " OR ".join(f'"{tok}"' for tok in tokens if tok)


class IndiceBusqueda:
    def __init__(self) -> None:
        self._modelo = SentenceTransformer(MODELO_EMBEDDINGS)
        self._cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
        self._coleccion = self._cliente.get_or_create_collection(COLECCION)
        self._total = self._coleccion.count()

        # Una conexión sqlite3 NO se puede compartir entre hilos, y el servidor
        # de la GUI (ThreadingHTTPServer) atiende cada petición en uno distinto:
        # guardar la conexión en el objeto hacía que la primera búsqueda
        # funcionara y la segunda muriera con "SQLite objects created in a
        # thread can only be used in that same thread". Se abre una conexión por
        # hilo, en modo solo lectura, y cada una se reusa mientras el hilo viva.
        self._local = threading.local()

    @property
    def _fts(self) -> sqlite3.Connection | None:
        """Conexión FTS5 propia del hilo que llama (None si no hay índice)."""
        if not DB_FTS.exists():
            return None
        conexion = getattr(self._local, "fts", None)
        if conexion is None:
            # solo lectura: el índice FTS5 se construye aparte con index/build_fts.py
            conexion = sqlite3.connect(f"file:{DB_FTS}?mode=ro", uri=True)
            self._local.fts = conexion
        return conexion

    def buscar(self, consulta: str, k: int = 8, fuentes: list[str] | None = None) -> list[dict]:
        """Busca en el índice; `fuentes` acota a esas entidades (None = todas).

        Al filtrar hay que pedir MÁS candidatos a cada método antes de fusionar:
        si se piden k*3 sin filtro y luego se descartan los de otras fuentes,
        una entidad pequeña como la SIC (0,7% del corpus) se quedaría sin
        candidatos casi siempre y el filtro parecería "no hay nada".
        """
        if self._total == 0:
            return []

        holgura = 1 if not fuentes else 8
        n_candidatos = min(k * 3 * holgura, self._total)

        embedding_consulta = self._modelo.encode([PREFIJO_CONSULTA + consulta]).tolist()
        consulta_vectorial = {
            "query_embeddings": embedding_consulta,
            "n_results": n_candidatos,
        }
        if fuentes:
            # Chroma filtra en su propio motor, así que aquí no hace falta
            # holgura: devuelve n_candidatos ya filtrados.
            consulta_vectorial["where"] = (
                {"fuente": fuentes[0]} if len(fuentes) == 1 else {"fuente": {"$in": list(fuentes)}}
            )
            consulta_vectorial["n_results"] = min(k * 3, self._total)
        resultado_vectorial = self._coleccion.query(**consulta_vectorial)
        ids_vectorial = resultado_vectorial["ids"][0]

        ids_fts: list[str] = []
        if self._fts is not None:
            tokens = _tokenizar(consulta)
            consulta_match = _consulta_fts(tokens)
            if consulta_match:
                cursor = self._fts.execute(
                    "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY rank LIMIT ?",
                    (consulta_match, n_candidatos),
                )
                ids_fts = [fila[0] for fila in cursor.fetchall()]
                if fuentes:
                    # El id empieza por la fuente ("sic:123::frag0"). El FTS no
                    # guarda la metadata, así que se filtra por ese prefijo.
                    prefijos = tuple(f"{f}:" for f in fuentes)
                    ids_fts = [i for i in ids_fts if i.startswith(prefijos)][: k * 3]

        rango_reciproco: dict[str, float] = {}
        for rango, doc_id in enumerate(ids_vectorial):
            rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + PESO_VECTORIAL / (K_RRF + rango)
        for rango, doc_id in enumerate(ids_fts):
            rango_reciproco[doc_id] = rango_reciproco.get(doc_id, 0) + PESO_BM25 / (K_RRF + rango)

        mejores = sorted(rango_reciproco.items(), key=lambda x: x[1], reverse=True)[:k]
        if not mejores:
            return []

        # solo se piden a Chroma los ~k documentos ganadores, no el corpus completo
        ids_finales = [doc_id for doc_id, _ in mejores]
        datos = self._coleccion.get(ids=ids_finales, include=["documents", "metadatas"])
        texto_por_id = dict(zip(datos["ids"], datos["documents"], strict=True))
        metadata_por_id = dict(zip(datos["ids"], datos["metadatas"], strict=True))

        resultados = []
        for doc_id, puntaje in mejores:
            if doc_id not in texto_por_id:
                continue  # inconsistencia rara entre Chroma y FTS5 (ej. reindex parcial)
            resultados.append(
                {
                    "id": doc_id,
                    "puntaje": round(puntaje, 4),
                    "texto": texto_por_id[doc_id],
                    **metadata_por_id[doc_id],
                }
            )
        return resultados


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    consulta = " ".join(sys.argv[1:]) or "incentivos bienestar social"
    indice = IndiceBusqueda()
    for r in indice.buscar(consulta, k=5):
        print(f"[{r['puntaje']}] {r['titulo_documento']} — {r['url_original']}")
        print("  " + r["texto"][:200].replace("\n", " "))
        print()
