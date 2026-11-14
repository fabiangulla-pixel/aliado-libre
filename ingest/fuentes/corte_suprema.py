"""Ingester de la Corte Suprema de Justicia — buscador de providencias por
texto completo (consultaprovidencias.cortesuprema.gov.co).

El frontend es una SPA (Vue) con shell vacío, pero habla con un backend
GraphQL propio en un dominio hermano no documentado hasta ahora:
`consultaprovidenciasbk.cortesuprema.gov.co/api`, sin autenticación ni CORS
restrictivo (confirmado con curl plano, sin necesidad de navegador).

- `getSearchResult`: lista resultados (título, ruta, magistrado, año) de una
  Sala, paginado con `start` de 10 en 10. El comodín `"*"` trae todo (`""`
  da 0) y `year` filtra por año, lo que permite recorrer y reanudar año a año.
  El filtro `autoSentencia` se ignora en el servidor: las sentencias se
  distinguen por el prefijo del título (SL laboral, SC civil; AL/AC son
  autos y STL/STC tutelas).
- `POST /downloadFile {"path": onlinePath}` devuelve el archivo original.
  `getContentSearch` NO sirve para ingerir: devuelve solo un extracto
  (~1.000 caracteres) alrededor del término, y con `"*"` responde 502
  (verificado 14-nov-2026; así se explica el "texto 502" de septiembre).

Cada fallo aparece como .pdf y .docx (a veces .doc): se agrupa por ruta sin
extensión y se prefiere el .docx, que se lee sin dependencias nuevas."""

from __future__ import annotations

import html
import re
import time
import zipfile
from datetime import date
from io import BytesIO

import requests
from pypdf import PdfReader

from ingest.schema import Documento

API_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    # el backend devuelve 502 sin Origin/Referer del frontend oficial
    "Origin": "https://consultaprovidencias.cortesuprema.gov.co",
    "Referer": "https://consultaprovidencias.cortesuprema.gov.co/",
}
DOWNLOAD_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile"
SALAS = ["Laboral", "Civil"]
PREFIJO_SENTENCIA = {"Laboral": "SL", "Civil": "SC"}
TAMANIO_PAGINA = 10  # lo que devuelve el API por página; no se parametriza
ANIO_MINIMO = 1990
PREFERENCIA_EXTENSION = {"docx": 0, "pdf": 1}


def _graphql(sesion: requests.Session, query: str, intentos: int = 3) -> dict:
    # verify=False: mismo problema de cadena de certificados incompleta en
    # servidores .gov.co ya visto en gestor_normativo.py y corte_constitucional.py.
    # El backend responde 502 de forma intermitente incluso con Origin/Referer
    # correctos (parece un proxy con poca capacidad, no un bloqueo real) — reintenta.
    ultimo_error: Exception | None = None
    for intento in range(intentos):
        try:
            r = sesion.post(API_URL, json={"query": query}, verify=False, timeout=30)
            r.raise_for_status()
            data = r.json()
            if "errors" in data:
                raise RuntimeError(data["errors"])
            return data["data"]
        except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as e:
            ultimo_error = e
            time.sleep(2 * (intento + 1))
    raise ultimo_error


def _buscar_pagina(sesion: requests.Session, sala: str, start: int, anio: int | str = "") -> list[dict]:
    query = f"""
    {{
      getSearchResult(searchQuery:{{
        query: "*"
        typeOfQuery: "{sala}"
        start: {start}
        isExact: false
        magistrate: ""
        year: "{anio}"
        autoSentencia: ""
        order: "NEW_FIRST"
        roomTutelas: ""
        addedQueries: []
      }}) {{
        searchResults {{ title onlinePath doctor ano }}
      }}
    }}
    """
    data = _graphql(sesion, query)
    return data["getSearchResult"]["searchResults"] or []


def _texto_docx(contenido: bytes) -> str:
    with zipfile.ZipFile(BytesIO(contenido)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    parrafos = []
    for p in re.split(r"</w:p>", xml):
        trozos = re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", p)
        if trozos:
            parrafos.append(html.unescape("".join(trozos)).strip())
    return "\n".join(x for x in parrafos if x)


def _texto_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(contenido)).pages)


def _texto_completo(sesion: requests.Session, ruta: str, intentos: int = 3) -> str | None:
    extension = ruta.rsplit(".", 1)[-1].lower()
    if extension not in PREFERENCIA_EXTENSION:
        return None
    for intento in range(intentos):
        try:
            r = sesion.post(DOWNLOAD_URL, json={"path": ruta}, verify=False, timeout=90)
            r.raise_for_status()
            texto = _texto_docx(r.content) if extension == "docx" else _texto_pdf(r.content)
            return texto.strip() or None
        except requests.exceptions.RequestException:
            time.sleep(2 * (intento + 1))
        except Exception:  # noqa: BLE001 - archivo corrupto o formato inesperado: se salta
            return None
    return None


def _identificador_desde_titulo(titulo: str) -> str:
    m = re.search(r"([A-Z]{1,3}\d{1,6}-\d{4})", titulo)
    return m.group(1) if m else titulo.rsplit(".", 1)[0]


def es_sentencia(sala: str, titulo: str) -> bool:
    return re.match(rf"{PREFIJO_SENTENCIA[sala]}\d", titulo) is not None


def _listar_anio(sesion: requests.Session, sala: str, anio: int, pausa_segundos: float) -> dict[str, dict]:
    """Una entrada por fallo (ruta sin extensión), con el archivo preferido."""
    por_fallo: dict[str, dict] = {}
    start = 0
    while True:
        pagina = _buscar_pagina(sesion, sala, start, anio)
        if not pagina:
            return por_fallo
        for item in pagina:
            ruta = item.get("onlinePath") or ""
            if not ruta or not es_sentencia(sala, item.get("title") or ""):
                continue
            base, _, ext = ruta.rpartition(".")
            rango = PREFERENCIA_EXTENSION.get(ext.lower(), 9)
            actual = por_fallo.get(base)
            if actual is None or rango < PREFERENCIA_EXTENSION.get(
                actual["onlinePath"].rsplit(".", 1)[-1].lower(), 9
            ):
                por_fallo[base] = item
        start += TAMANIO_PAGINA
        time.sleep(pausa_segundos / 4)


def crawl(
    max_documentos: int = 500,
    pausa_segundos: float = 1.0,
    al_guardar=None,
    documentos_previos: list[Documento] | None = None,
    salas: list[str] | None = None,
    anios: list[int] | None = None,
    anios_hechos: set[tuple[str, int]] | None = None,
    al_terminar_anio=None,
) -> list[Documento]:
    """Recorre sala por sala y año por año (del más reciente al más viejo).
    Los fallos ya presentes en `documentos_previos` no se vuelven a bajar y los
    pares (sala, año) de `anios_hechos` ni se listan. `al_terminar_anio(sala,
    anio)` se llama solo si el año quedó completo, no al cortar por tope."""
    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    anios = anios or list(range(date.today().year, ANIO_MINIMO - 1, -1))
    anios_hechos = anios_hechos or set()

    documentos: list[Documento] = list(documentos_previos or [])
    vistos = {d.metadata["ruta"].rsplit(".", 1)[0] for d in documentos if d.metadata.get("ruta")}
    ids = {d.id for d in documentos}

    for sala in salas or SALAS:
        for anio in anios:
            if (sala, anio) in anios_hechos:
                continue
            if len(documentos) >= max_documentos:
                return documentos
            nuevos_en_anio = 0
            for base, item in _listar_anio(sesion, sala, anio, pausa_segundos).items():
                # el mismo fallo a veces está bajo dos carpetas (p. ej. sala de descongestión)
                if (
                    base in vistos
                    or f"corte_suprema:{sala.lower()}:{_identificador_desde_titulo(item['title'])}" in ids
                ):
                    continue
                if len(documentos) >= max_documentos:
                    if al_guardar is not None:
                        al_guardar(documentos)
                    return documentos
                ruta = item["onlinePath"]
                texto = _texto_completo(sesion, ruta)
                time.sleep(pausa_segundos)
                if not texto or len(texto) < 100:
                    continue
                vistos.add(base)
                titulo = item.get("title", ruta)
                identificador = _identificador_desde_titulo(titulo)
                ids.add(f"corte_suprema:{sala.lower()}:{identificador}")
                documentos.append(
                    Documento(
                        id=f"corte_suprema:{sala.lower()}:{identificador}",
                        fuente="corte_suprema",
                        tipo="sentencia",
                        identificador=identificador,
                        titulo=f"Corte Suprema - Sala {sala} - Sentencia {identificador}",
                        fecha=str(item.get("ano") or anio),
                        texto=texto,
                        url_original="https://consultaprovidencias.cortesuprema.gov.co/",
                        metadata={"sala": sala, "magistrado": item.get("doctor"), "ruta": ruta},
                    )
                )
                nuevos_en_anio += 1
                if al_guardar is not None and nuevos_en_anio % 50 == 0:
                    al_guardar(documentos)
            if al_guardar is not None:
                al_guardar(documentos)
            if al_terminar_anio is not None:
                al_terminar_anio(sala, anio)

    return documentos
