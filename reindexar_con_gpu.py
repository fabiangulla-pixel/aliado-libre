#!/usr/bin/env python3
"""Reindexación completa con chunking mejorado, usando GPU."""

import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import chromadb
import torch
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest.chunking import _modo_troceo, fragmentar
from ingest.schema import Documento

# TF32 solo al INDEXAR. Medido el 11-sep-2026 sobre 3.000 pasajes y 60 consultas
# reales, con las consultas codificadas siempre en fp32 estricto (que es como
# corre la busqueda):
#
#   fp32 estricto   19 pasajes/s   (referencia)
#   TF32            32 pasajes/s   conjunto top-5 identico 60/60, top-40 92%
#   fp16            78 pasajes/s   conjunto top-5 solo 51/60, top-40 36/60
#
# fp16 queda descartado: cambia QUE documentos se recuperan en el 15% de las
# consultas, y eso no es una optimizacion sino otro indice. TF32 no cambia el
# conjunto de los cinco primeros, que es lo que mide el recall@5; si altera el
# top-40 en un 8% de casos, en la cola de la ventana del reranker.
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.set_float32_matmul_precision("high")


# Las rutas se toman de index.buscar, no se redeclaran aqui: tener dos copias
# es como el indexador y el buscador acabaron apuntando a sitios distintos el
# 9-sep-2026. Se respetan asi ALIADO_DIR_INDICE / ALIADO_DB_FTS.
from index.buscar import (  # noqa: E402
    COLECCION,
    DB_FTS,
    DIR_INDICE,
    MODELO_EMBEDDINGS,
    PREFIJO_PASAJE,
)

CLAVE_TROCEO = "troceo"
CLAVE_CORPUS = "corpus"
CLAVE_DOCUMENTOS = "documentos"


def huella_corpus(documentos: list[Documento]) -> str:
    """Identifica la instantanea del corpus con la que se construyo un indice.

    Sin esto el corpus es una variable suelta del experimento, y lo fue: el
    12-sep-2026 se planteo reindexar dos horas para explicar por que el recall
    habia bajado de 33,5% (7-sep) a 24,5%, dando por hecho que el corpus era el
    mismo. No lo era. Correr el troceo del 7-sep sobre el corpus de hoy da
    1.042.474 fragmentos, no los 718.388 que tenia aquel indice: entre una
    medicion y otra el corpus habia cambiado, asi que las dos cifras nunca
    fueron comparables y ningun reindexado iba a recuperar el punto de partida.
    Dos recalls solo se pueden comparar si esta huella coincide.
    Ver [[feedback_hardware_es_variable_del_experimento]].
    """
    h = hashlib.sha256()
    for doc in sorted(documentos, key=lambda d: d.id):
        h.update(doc.id.encode("utf-8"))
        h.update(str(len(doc.texto)).encode("ascii"))
    return h.hexdigest()[:16]


def anotar_corpus(coleccion, documentos: list[Documento]) -> None:
    """Graba la huella, o avisa si el indice se esta ampliando con otro corpus."""
    huella = huella_corpus(documentos)
    metadatos = dict(coleccion.metadata or {})
    anotada = metadatos.get(CLAVE_CORPUS)
    if anotada and anotada != huella:
        raise SystemExit(
            f"Este indice se construyo con el corpus {anotada} "
            f"({metadatos.get(CLAVE_DOCUMENTOS, '?')} documentos) y data/raw es ahora "
            f"{huella} ({len(documentos)} documentos). Reanudar mezclaria dos corpus y "
            "el recall resultante no seria comparable con ninguna cifra anterior. "
            "Indexar en un directorio nuevo con ALIADO_DIR_INDICE."
        )
    coleccion.modify(metadata={**metadatos, CLAVE_CORPUS: huella, CLAVE_DOCUMENTOS: len(documentos)})
    print(f"Corpus {huella} ({len(documentos)} documentos)")


def comprobar_troceo_compatible(coleccion) -> None:
    """Impide reanudar un indice con un troceo distinto del que lo construyo.

    Los ids de fragmento son `documento::fragN` en los dos modos, asi que al
    reanudar el filtro `ya_estan` los da por hechos y se salta casi todo: el
    indice queda mitad de un troceo y mitad del otro, con el conteo cuadrando y
    sin un solo error. Se anota el modo en los metadatos de la coleccion y se
    exige que coincida.
    """
    modo = _modo_troceo()
    metadatos = dict(coleccion.metadata or {})
    anotado = metadatos.get(CLAVE_TROCEO)
    if anotado is None:
        if coleccion.count():
            raise SystemExit(
                f"El indice de {DIR_INDICE} no dice con que troceo se construyo y ya "
                f"tiene {coleccion.count()} fragmentos. Reanudarlo con ALIADO_TROCEO="
                f"{modo} puede mezclar dos troceos sin avisar. Indexar en un "
                "directorio nuevo (ALIADO_DIR_INDICE) o borrar este a mano."
            )
        coleccion.modify(metadata={**metadatos, CLAVE_TROCEO: modo})
        return
    if anotado != modo:
        raise SystemExit(
            f"Este indice se construyo con ALIADO_TROCEO={anotado} y ahora se pide "
            f"{modo}. Los ids coinciden entre troceos, asi que reanudar dejaria un "
            "indice mezclado que cuadra en el conteo y miente en la medicion. "
            "Usar ALIADO_DIR_INDICE para indexar aparte."
        )


def cargar_documentos(dir_raw: Path) -> list[Documento]:
    documentos = []
    for archivo in sorted(dir_raw.glob("*.json")):
        if archivo.name.startswith("_"):
            continue
        data = json.loads(archivo.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        for item in items:
            documentos.append(Documento(**item))
    return documentos


def reindexar(dir_raw: Path) -> None:
    documentos = cargar_documentos(dir_raw)
    if not documentos:
        print(f"No hay documentos en {dir_raw}")
        return

    print(f"Cargados {len(documentos)} documentos")

    fragmentos = []
    for i, doc in enumerate(documentos, 1):
        frags = fragmentar(doc)
        fragmentos.extend(frags)
        if i % 50 == 0:
            print(f"  {i}/{len(documentos)} documentos procesados ({len(fragmentos)} fragmentos)")

    print(f"Total: {len(fragmentos)} fragmentos después del chunking mejorado")

    # El índice anterior NO se borra: se reanuda sobre él. La versión destructiva
    # de este script borraba Chroma y el FTS antes de empezar, así que una corrida
    # interrumpida dejaba el proyecto sin índice utilizable y sin aviso — fue lo
    # que pasó el 9-sep-2026, que terminó con 158.000 fragmentos de los 226.000
    # anunciados y el índice léxico borrado y nunca reconstruido.
    # Cargar modelo con GPU (device_map automático)
    print("Cargando modelo de embeddings (GPU si está disponible)...")
    modelo = SentenceTransformer(MODELO_EMBEDDINGS)
    print(f"  Modelo en device: {modelo.device}")

    # Crear cliente Chroma
    cliente = chromadb.PersistentClient(path=str(DIR_INDICE))
    coleccion = cliente.get_or_create_collection(COLECCION)
    comprobar_troceo_compatible(coleccion)
    anotar_corpus(coleccion, documentos)

    # Reanudar: lo que ya está indexado no se vuelve a codificar. Sin esto, una
    # corrida de horas que se cae obliga a empezar de cero.
    ya_estan: set[str] = set()
    if coleccion.count():
        desplazamiento = 0
        while True:
            pagina = coleccion.get(include=[], limit=50000, offset=desplazamiento)
            if not pagina["ids"]:
                break
            ya_estan.update(pagina["ids"])
            desplazamiento += len(pagina["ids"])
        print(f"Ya indexados: {len(ya_estan)} fragmentos; se reanuda sobre ellos")
    pendientes = [f for f in fragmentos if f.id not in ya_estan]
    print(f"Pendientes de indexar: {len(pendientes)}")

    # Upsert incremental con GPU
    tamanio_lote = 1000
    total = len(pendientes)
    for inicio in range(0, total, tamanio_lote):
        lote = pendientes[inicio : inicio + tamanio_lote]
        textos = [f.texto for f in lote]

        # batch_size > 1 usa más memoria pero aprovecha mejor la GPU
        print(f"  Codificando fragmentos {inicio}-{min(inicio + tamanio_lote, total)}/{total}...")
        embeddings = modelo.encode(
            [PREFIJO_PASAJE + t for t in textos], batch_size=64, show_progress_bar=True
        ).tolist()

        ids = [f.id for f in lote]
        metadatas = [
            {
                "documento_id": f.documento_id,
                "fuente": f.fuente,
                "identificador_documento": f.identificador_documento,
                "titulo_documento": f.titulo_documento,
                "url_original": f.url_original,
                "orden": f.orden,
            }
            for f in lote
        ]

        print("  Subiendo lote...")
        coleccion.upsert(ids=ids, embeddings=embeddings, documents=textos, metadatas=metadatas)

    indexados = coleccion.count()
    print(f"\nChroma: {indexados} fragmentos ({len(fragmentos)} esperados)")
    if indexados < len(fragmentos):
        raise SystemExit(
            f"Reindexacion INCOMPLETA: faltan {len(fragmentos) - indexados} fragmentos. "
            "Volver a correr este script; reanuda donde quedo."
        )

    # El indice lexico se reconstruye aqui, encadenado: dejarlo como un segundo
    # paso manual es justo lo que fallo el 9-sep-2026.
    print("Reconstruyendo el indice lexico FTS5...")
    if DB_FTS.exists():
        DB_FTS.unlink()
    from index.build_fts import construir as construir_fts

    construir_fts()
    print(f"\nReindexacion completada: {indexados} fragmentos + indice lexico")
    print(f"Indices en: {DIR_INDICE}")


if __name__ == "__main__":
    dir_por_defecto = Path(__file__).resolve().parent / "data" / "raw"
    dir_raw = Path(sys.argv[1]) if len(sys.argv) > 1 else dir_por_defecto
    reindexar(dir_raw)
