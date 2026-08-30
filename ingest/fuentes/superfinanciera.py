"""Ingester de la Superintendencia Financiera de Colombia — Buscador de
Conceptos Jurídicos y Jurisprudencia (catálogo bibliográfico ABCD/ISIS, no
un buscador moderno). Se accede vía GET con paginación simple `desde`/`count`
sobre `base=juris`; cada registro trae metadata rica (resumen, temas,
documento fuente) y casi siempre un enlace "Archivo de texto" descargable
(`loader.php?...idFile=NNN`) con el contenido completo."""

from __future__ import annotations

import re
import time
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from docx import Document as DocumentoWord
from pypdf import PdfReader

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


FIRMAS_BINARIAS_CONOCIDAS = (
    b"ID3",  # MP3 con tag ID3v2 — el tag en sí puede traer XML/texto legible
    # (metadata XMP), lo que engañaba una heurística que solo miraba el inicio
    b"\xff\xfb",
    b"\xff\xf3",
    b"\xff\xf2",  # MP3 sin tag (frame sync MPEG directo)
    b"RIFF",  # WAV/AVI
    b"\x00\x00\x00",  # inicio típico de contenedores MP4/MOV (ftyp box)
)


def _parece_texto(contenido: bytes) -> bool:
    """Heurística para no decodificar binarios como si fueran texto plano.
    Bug real (segunda y tercera vuelta): además de .docx, el catálogo sirve
    audios (.mp3, grabaciones de audiencias/fallos) bajo el mismo enlace
    "Archivo de texto" — decodificarlos con latin1 (que nunca falla, mapea
    cualquier byte) producía "texto" de decenas de MB de basura por
    documento. La primera versión de esta heurística solo miraba los
    primeros 8KB, que en un MP3 con tag ID3v2 pueden ser casi todo texto
    legible (metadata XMP embebida) — un documento de 114 millones de
    caracteres se coló así. Ahora se muestrea inicio, medio y final."""
    if contenido[:4] in FIRMAS_BINARIAS_CONOCIDAS or contenido[:3] == b"ID3":
        return False
    if not contenido:
        return False
    n = len(contenido)
    puntos_muestra = [0, n // 2, max(0, n - 8192)]
    for inicio in puntos_muestra:
        muestra = contenido[inicio : inicio + 8192]
        if not muestra:
            continue
        bytes_de_control = sum(1 for b in muestra if b < 9 or (13 < b < 32))
        if (bytes_de_control / len(muestra)) >= 0.01:
            return False
    return True


def _extraer_texto_binario(contenido: bytes) -> str | None:
    """El "Archivo de texto" del catálogo puede ser, a pesar del nombre del
    enlace: un .docx (Word Open XML), un .pdf, un audio (.mp3) u
    ocasionalmente texto plano real. Se detecta el formato por firma de
    bytes — nunca por la extensión del enlace, que no es confiable — y los
    formatos no soportados (audio, video, etc.) se descartan explícitamente
    en vez de decodificarlos a ciegas. Además de la detección por formato,
    hay un tope duro de tamaño de salida — red de seguridad ante un cuarto
    formato binario no previsto que engañe la heurística (ya van dos)."""
    TOPE_CARACTERES = 2_000_000  # ningún concepto/sentencia real es tan largo

    def _con_tope(texto: str | None) -> str | None:
        if texto is not None and len(texto) > TOPE_CARACTERES:
            return None
        return texto

    if contenido[:2] == b"PK":  # .docx (zip) — Word Open XML
        try:
            documento = DocumentoWord(BytesIO(contenido))
            return _con_tope("\n".join(p.text for p in documento.paragraphs if p.text.strip()))
        except Exception:
            return None
    if contenido[:4] == b"%PDF":
        try:
            lector = PdfReader(BytesIO(contenido))
            return _con_tope("\n".join(p.extract_text() or "" for p in lector.pages).strip())
        except Exception:
            return None
    if not _parece_texto(contenido):
        return None  # binario no soportado (audio, video, imagen, ...)
    for codec in ("utf-8", "iso-8859-1"):
        try:
            return _con_tope(contenido.decode(codec))
        except UnicodeDecodeError:
            continue
    return None


def _descargar_archivo_texto(sesion: requests.Session, bloque_html: str) -> str | None:
    m = re.search(r"idFile=(\d+)", bloque_html)
    if not m:
        return None
    params = {"lServicio": "Tools2", "lTipo": "descargas", "lFuncion": "descargar", "idFile": m.group(1)}
    r = sesion.get(DESCARGA_URL, params=params, timeout=30)
    if r.status_code != 200 or not r.content:
        return None
    return _extraer_texto_binario(r.content)


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


def crawl(
    max_documentos: int = 500,
    pausa_segundos: float = 0.5,
    al_guardar=None,
    documentos_previos: list[Documento] | None = None,
) -> list[Documento]:
    """Si se pasa `documentos_previos` (de una corrida anterior), reanuda
    desde el índice global donde se quedó en vez de reempezar desde el
    registro 1 — la paginación del catálogo es puramente secuencial."""
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    documentos_previos = documentos_previos or []
    documentos: list[Documento] = list(documentos_previos)
    indice_global = max((int(d.id.split(":")[1]) for d in documentos_previos), default=0)
    desde = indice_global + 1  # el motor ABCD/ISIS es 1-indexado; desde=0 devuelve el formulario vacío

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
