"""Ingester de la SIC (Superintendencia de Industria y Comercio) — decisiones
jurisdiccionales por competencia desleal y propiedad industrial.

El frontend habla directo con un Elasticsearch expuesto públicamente
(relatoria.sic.gov.co/sic-relatoria-idx/_search) para metadata, pero el
texto vive en PDFs en un bucket S3 privado. Se resuelve con un endpoint
Lambda público que devuelve una URL firmada temporal para cada PDF, sin
autenticación."""

from __future__ import annotations

import json
import time
import urllib.parse
from io import BytesIO

import requests
from pypdf import PdfReader

from ingest.schema import Documento

ES_BASE = "https://relatoria.sic.gov.co/sic-relatoria-idx/_search"
SIGNED_URL_BASE = "https://m0s03uyzg3.execute-api.us-east-1.amazonaws.com/prod/get-signed-url/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TAMANIO_PAGINA = 25


def _query(sesion: requests.Session, desde: int, tamanio: int) -> dict:
    source = {"query": {"match_all": {}}, "from": desde, "size": tamanio}
    url = f"{ES_BASE}?source={urllib.parse.quote(json.dumps(source))}&source_content_type=application/json"
    r = sesion.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def _descargar_texto_pdf(sesion: requests.Session, ruta_s3: str) -> str | None:
    url_firma = SIGNED_URL_BASE + urllib.parse.quote(ruta_s3, safe="")
    r_firma = sesion.get(url_firma, timeout=30)
    if r_firma.status_code != 200:
        return None
    signed_url = r_firma.json().get("signedUrl")
    if not signed_url:
        return None

    r_pdf = sesion.get(signed_url, timeout=60)
    if r_pdf.status_code != 200:
        return None

    try:
        lector = PdfReader(BytesIO(r_pdf.content))
        return "\n".join(p.extract_text() or "" for p in lector.pages).strip()
    except Exception:
        return None


def _a_documento(sesion: requests.Session, hit: dict) -> Documento | None:
    src = hit["_source"]
    info = src.get("informacion") or {}
    resumen = src.get("documento_resumen") or {}
    ruta_s3 = resumen.get("url_documento_pdf_s3")
    if not ruta_s3:
        return None

    texto = _descargar_texto_pdf(sesion, ruta_s3)
    if not texto or len(texto) < 100:
        return None

    numero_expediente = info.get("numero_expediente", "")
    ano = info.get("ano_expediente", "")
    identificador = f"{ano}-{numero_expediente}" if numero_expediente else hit["_id"]

    return Documento(
        id=f"sic:{hit['_id']}",
        fuente="sic",
        tipo="sentencia",
        identificador=identificador,
        titulo=f"SIC {info.get('tipo_providencia', 'Providencia')} {identificador}",
        fecha=info.get("fecha_providencia"),
        texto=texto,
        url_original="https://relatoria.sic.gov.co/#/",
        metadata={
            "tipo_proceso": info.get("tipo_proceso"),
            "tipo_providencia": info.get("tipo_providencia"),
            "tesauro": [
                t.get("descriptor", {}).get("nombre")
                for t in (src.get("tesauro") or [])
                if t.get("descriptor", {}).get("nombre")
            ],
        },
    )


def crawl(max_documentos: int = 200, pausa_segundos: float = 1.5, al_guardar=None) -> list[Documento]:
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    documentos: list[Documento] = []
    desde = 0

    while len(documentos) < max_documentos:
        restante = max_documentos - len(documentos)
        resultado = _query(sesion, desde, min(TAMANIO_PAGINA, restante))
        hits = resultado["hits"]["hits"]
        if not hits:
            break

        for hit in hits:
            doc = _a_documento(sesion, hit)
            if doc is not None:
                documentos.append(doc)
            time.sleep(pausa_segundos)

        desde += len(hits)
        if al_guardar is not None:
            al_guardar(documentos)

    return documentos
