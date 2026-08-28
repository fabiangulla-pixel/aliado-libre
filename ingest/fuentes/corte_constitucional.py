"""Ingester de la Corte Constitucional — jurisprudencia (sentencias y autos).

API interna JSON (Elasticsearch envuelto) en /relatoria/buscador_new/. Se
enumera por año (fini/ffin), no por término de búsqueda: con maxprov alto
(2000) un solo request por año trae todas las providencias de ese año,
mucho más eficiente que paginar de a poco. ~35 requests cubren 1992-hoy.

El campo `prov_sintesis` ya trae un resumen jurídico sustancial del caso,
sin necesitar una segunda petición por documento para el texto completo."""

from __future__ import annotations

import time

import requests

from ingest.schema import Documento

BASE = "https://www.corteconstitucional.gov.co/relatoria/buscador_new/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
MAXPROV_POR_ANIO = 3000  # holgado sobre el máximo observado (~1000/año)


def _buscar_por_anio(sesion: requests.Session, anio: int) -> list[dict]:
    params = {
        "searchOption": "texto",
        "fini": f"{anio}-01-01",
        "ffin": f"{anio}-12-31",
        "buscar_por": "",
        "maxprov": MAXPROV_POR_ANIO,
        "slop": 1,
        "accion": "search",
        "tipo": "json",
    }
    r = sesion.get(BASE, params=params, verify=False, timeout=60)
    r.raise_for_status()
    return r.json()["data"]["hits"]["hits"]


def _a_documento(hit: dict) -> Documento | None:
    src = hit["_source"]
    sentencia = src.get("prov_sentencia")
    sintesis = (src.get("prov_sintesis") or "").strip()
    if not sentencia or sintesis in ("", "Sin información"):
        return None

    ruta = src.get("rutahtml", "")
    url = f"https://www.corteconstitucional.gov.co/relatoria/{ruta}" if ruta else ""

    return Documento(
        id=f"corte_constitucional:{hit['_id']}",
        fuente="corte_constitucional",
        tipo="sentencia",
        identificador=sentencia,
        titulo=f"Sentencia {sentencia} - Corte Constitucional",
        fecha=src.get("prov_f_sentencia"),
        texto=sintesis,
        url_original=url,
        metadata={
            "tema": src.get("prov_tema"),
            "tipo_providencia": src.get("prov_tipo"),
            "expediente": src.get("prov_expediente"),
            "magistrados": src.get("prov_magistrados") or [],
            "sala": src.get("sala_seguimiento"),
        },
    )


def crawl(
    anio_inicio: int = 1992,
    anio_fin: int | None = None,
    pausa_segundos: float = 2.0,
    al_guardar=None,
) -> list[Documento]:
    """Un request por año (fini/ffin), no por documento -> el corpus completo
    de la Corte Constitucional cabe en ~35 requests. pausa_segundos generosa
    porque este dominio ya nos bloqueó temporalmente una vez por exceso de
    pruebas seguidas."""
    import datetime

    anio_fin = anio_fin or datetime.date.today().year

    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    documentos: list[Documento] = []

    for anio in range(anio_inicio, anio_fin + 1):
        hits = _buscar_por_anio(sesion, anio)
        for hit in hits:
            doc = _a_documento(hit)
            if doc is not None:
                documentos.append(doc)

        if al_guardar is not None:
            al_guardar(documentos)
        time.sleep(pausa_segundos)

    return documentos
