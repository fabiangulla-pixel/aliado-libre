"""Ingester de la Superintendencia de Sociedades (Tesauro) — conceptos jurídicos
y jurisprudencia mercantil. A diferencia de la SIC, el texto completo viene
embebido directo en Elasticsearch (`documento_principal.contenido_archivo`),
sin depender de descargar PDFs de S3."""

from __future__ import annotations

import json
import time
import urllib.parse

import requests

from ingest.schema import Documento

ES_BASE = "https://admin.es.prod.ssociedades.nuvu.cc/index_thesaurus/_search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TAMANIO_PAGINA = 50


def _query(despues_de: str | None, tamanio: int) -> dict:
    # search_after y no from/size: Elasticsearch corta from+size en 10.000 y el
    # tesauro ya tiene 14.738 (nov-2026). El orden por _id además evita
    # duplicados entre páginas (visto: 1 en 5.000 con from/size sin sort).
    source = {"size": tamanio, "query": {"match_all": {}}, "sort": [{"_id": "asc"}]}
    if despues_de is not None:
        source["search_after"] = [despues_de]
    url = f"{ES_BASE}?source={urllib.parse.quote(json.dumps(source))}&source_content_type=application/json"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def _a_documento(hit: dict) -> Documento | None:
    src = hit["_source"]
    principal = src.get("documento_principal") or {}
    texto = (principal.get("contenido_archivo") or "").strip()
    if len(texto) < 100:
        return None

    info = src.get("informacion") or {}
    titulo = src.get("titulo") or f"Concepto {hit['_id']}"

    return Documento(
        id=f"supersociedades:{hit['_id']}",
        fuente="supersociedades",
        tipo="concepto",
        identificador=info.get("consecutivo") or info.get("numero_radicado") or hit["_id"],
        titulo=titulo,
        fecha=info.get("fecha_sentencia"),
        texto=texto,
        url_original=f"https://tesauro.supersociedades.gov.co/results/{hit['_id']}",
        metadata={
            "tipo_contenido": info.get("tipo_contenido"),
            "descriptores": [
                d.get("descriptor_principal")
                for d in (src.get("descriptores") or [])
                if d.get("descriptor_principal")
            ],
            "fuentes_juridicas": [
                {"fuente": f.get("fuente"), "estado": f.get("estado")}
                for f in (src.get("fuentes_juridicas") or [])
                if f.get("fuente")
            ],
        },
    )


def crawl(
    max_documentos: int = 200,
    pausa_segundos: float = 1.0,
    al_guardar=None,
    documentos_previos: list[Documento] | None = None,
) -> list[Documento]:
    """Los previos se conservan tal cual (pueden traer el texto ya anonimizado)
    y no se reemplazan por la versión recién bajada."""
    documentos: list[Documento] = list(documentos_previos or [])
    ids_vistos: set[str] = {d.id for d in documentos}
    despues_de: str | None = None

    while len(documentos) < max_documentos:
        hits = _query(despues_de, TAMANIO_PAGINA)["hits"]["hits"]
        if not hits:
            break

        for hit in hits:
            if len(documentos) >= max_documentos:
                break
            if f"supersociedades:{hit['_id']}" in ids_vistos:
                continue
            doc = _a_documento(hit)
            if doc is not None:
                ids_vistos.add(doc.id)
                documentos.append(doc)

        despues_de = hits[-1]["_id"]
        if al_guardar is not None:
            al_guardar(documentos)
        time.sleep(pausa_segundos)

    return documentos
