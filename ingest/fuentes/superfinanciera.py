"""Ingester de la Superintendencia Financiera de Colombia — Buscador de
Conceptos Jurídicos y Jurisprudencia (catálogo bibliográfico ABCD/ISIS, no
un buscador moderno). Se accede vía GET con paginación simple `desde`/`count`
sobre `base=juris`; cada registro trae metadata rica (resumen, temas,
documento fuente) y casi siempre un enlace "Archivo de texto" descargable
(`loader.php?...idFile=NNN`) con el contenido completo."""

from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

from ingest.schema import Documento

BUSCADOR_URL = "https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php"
DESCARGA_URL = "https://www.superfinanciera.gov.co/loader.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TAMANIO_PAGINA = 25


def _obtener_pagina(sesion: requests.Session, desde: int) -> str:
    # Construida como URL cruda (no via params=) porque el motor ABCD/ISIS
    # distingue entre "prefijo" sin valor (funciona) y "prefijo=" con valor
    # vacío (devuelve el formulario en blanco, sin resultados).
    url = f"{BUSCADOR_URL}?base=juris&Opcion=libre&Expresion=$&prefijo&desde={desde}&count={TAMANIO_PAGINA}"
    r = sesion.get(url, timeout=30)
    r.raise_for_status()
    return r.content.decode("iso-8859-1", errors="replace")


def _texto_campo(bloque_html: str, etiqueta: str) -> str | None:
    m = re.search(
        rf"<td class=td1[^>]*>{re.escape(etiqueta)}:?\s*</td>\s*<td class=td2[^>]*>(.*?)</td>",
        bloque_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    texto = BeautifulSoup(m.group(1), "html.parser").get_text(" ", strip=True)
    return texto or None


def _descargar_archivo_texto(sesion: requests.Session, bloque_html: str) -> str | None:
    m = re.search(r"idFile=(\d+)", bloque_html)
    if not m:
        return None
    params = {"lServicio": "Tools2", "lTipo": "descargas", "lFuncion": "descargar", "idFile": m.group(1)}
    r = sesion.get(DESCARGA_URL, params=params, timeout=30)
    if r.status_code != 200 or not r.content:
        return None
    for codec in ("utf-8", "iso-8859-1"):
        try:
            return r.content.decode(codec)
        except UnicodeDecodeError:
            continue
    return None


def _a_documento(sesion: requests.Session, bloque_html: str, indice_global: int) -> Documento | None:
    titulo = _texto_campo(bloque_html, "T&iacute;tulo de la norma") or _texto_campo(
        bloque_html, "Título de la norma"
    )
    concepto = _texto_campo(bloque_html, "Concepto")
    resumen = _texto_campo(bloque_html, "Resumen") or ""
    if not titulo and not concepto:
        return None

    texto_completo = _descargar_archivo_texto(sesion, bloque_html)
    texto = texto_completo if texto_completo and len(texto_completo) > len(resumen) else resumen
    if not texto or len(texto) < 40:
        return None

    identificador = concepto or titulo or f"registro_{indice_global}"
    fecha = None
    m_fecha = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", concepto or titulo or "")
    if m_fecha:
        from ingest.normalizar import fecha_es_a_iso

        fecha = fecha_es_a_iso(m_fecha.group(0))

    return Documento(
        id=f"superfinanciera:{indice_global}:{identificador[:60]}",
        fuente="superfinanciera",
        tipo="concepto",
        identificador=identificador,
        titulo=titulo or identificador,
        fecha=fecha,
        texto=texto,
        url_original=f"{BUSCADOR_URL}?base=juris&Opcion=libre&Expresion=$",
        metadata={"resumen": resumen or None},
    )


def crawl(max_documentos: int = 500, pausa_segundos: float = 0.5, al_guardar=None) -> list[Documento]:
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    documentos: list[Documento] = []
    desde = 1  # el motor ABCD/ISIS es 1-indexado; desde=0 devuelve el formulario vacío
    indice_global = 0

    while len(documentos) < max_documentos:
        html = _obtener_pagina(sesion, desde)
        bloques = html.split('<div id="registro">')[1:]
        if not bloques:
            break

        for bloque in bloques:
            indice_global += 1
            if len(documentos) >= max_documentos:
                break
            doc = _a_documento(sesion, bloque, indice_global)
            if doc is not None:
                documentos.append(doc)
            time.sleep(pausa_segundos)

        desde += TAMANIO_PAGINA
        if al_guardar is not None:
            al_guardar(documentos)

    return documentos
