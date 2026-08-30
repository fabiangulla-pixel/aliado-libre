"""Ingester de la Corte Suprema de Justicia — buscador de providencias por
texto completo (consultaprovidencias.cortesuprema.gov.co).

El frontend es una SPA (Vue) con shell vacío, pero habla con un backend
GraphQL propio en un dominio hermano no documentado hasta ahora:
`consultaprovidenciasbk.cortesuprema.gov.co/api`, sin autenticación ni CORS
restrictivo (confirmado con curl plano, sin necesidad de navegador).

Dos queries cubren todo:
- `getSearchResult`: lista resultados (título, ruta, magistrado) para una
  Sala (Civil/Laboral/Penal/Tutelas) + término de búsqueda, paginado con
  `start`. El término comodín `"*"` trae TODO el corpus de la sala (a
  diferencia de `""`, que devuelve 0 resultados) — sin él no hay forma de
  enumerar exhaustivamente.
- `getContentSearch`: dado el `onlinePath` devuelto arriba, trae el texto
  completo ya extraído del PDF/DOCX (campo `contentText`, HTML con <mark>
  en los términos resaltados — se limpia con BeautifulSoup).

Advertencia de escala: cada Sala trae decenas a cientos de miles de
resultados con "*" (Civil ~109k, Laboral ~302k, Penal ~218k, Tutelas ~394k
al 29-ago-2026), y cada resultado aparece duplicado en .pdf/.docx — hace
falta deduplicar por ruta sin extensión. Ingestar el corpus completo implica
cientos de miles de llamadas a getContentSearch; usar `max_documentos` para
ir escalando por lotes con checkpoint, igual que Gestor Normativo."""

from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

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
SALAS = ["Civil", "Laboral", "Penal", "Tutelas"]
TAMANIO_PAGINA = 25  # observado en el frontend; el API no lo parametriza


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


def _buscar_pagina(sesion: requests.Session, sala: str, start: int) -> list[dict]:
    query = f"""
    {{
      getSearchResult(searchQuery:{{
        query: "*"
        typeOfQuery: "{sala}"
        start: {start}
        isExact: false
        magistrate: ""
        year: ""
        autoSentencia: ""
        order: "NEW_FIRST"
        roomTutelas: ""
        addedQueries: []
      }}) {{
        searchResults {{ title onlinePath doctor }}
      }}
    }}
    """
    data = _graphql(sesion, query)
    return data["getSearchResult"]["searchResults"] or []


def _texto_completo(sesion: requests.Session, ruta: str, sala: str) -> str | None:
    ruta_escapada = ruta.replace("\\", "\\\\").replace('"', '\\"')
    query = f"""
    {{
      getContentSearch(previewDocument:{{id: "{ruta_escapada}" room: "{sala}" text: "*"}}) {{
        contentText
      }}
    }}
    """
    try:
        data = _graphql(sesion, query)
    except Exception:
        return None
    html = data.get("getContentSearch", {}).get("contentText")
    if not html:
        return None
    return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)


def _identificador_desde_titulo(titulo: str) -> str:
    m = re.search(r"([A-Z]{1,3}\d{3,5}-\d{4})", titulo)
    return m.group(1) if m else titulo.rsplit(".", 1)[0]


def crawl(
    max_documentos: int = 500,
    pausa_segundos: float = 1.0,
    al_guardar=None,
    documentos_previos: list[Documento] | None = None,
) -> list[Documento]:
    """Si se pasa `documentos_previos`, no se vuelve a pedir el texto completo
    de rutas ya vistas (dedupe exacto vía `metadata["ruta"]`), y por cada Sala
    se salta el listado hasta un `start` estimado a partir de cuántos
    documentos de esa Sala ya se tienen — el orden `NEW_FIRST` es estable
    entre corridas cercanas en el tiempo, así que no hace falta re-listar
    desde cero (cada documento real aparece ~2 veces en los resultados,
    .pdf y .docx, de ahí el factor 2 en la estimación)."""
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    documentos_previos = documentos_previos or []
    documentos: list[Documento] = list(documentos_previos)
    vistos: set[str] = {
        d.metadata["ruta"].rsplit(".", 1)[0] for d in documentos_previos if d.metadata.get("ruta")
    }

    documentos_previos_por_sala: dict[str, int] = {}
    for d in documentos_previos:
        sala_previa = d.metadata.get("sala", "")
        documentos_previos_por_sala[sala_previa] = documentos_previos_por_sala.get(sala_previa, 0) + 1

    for sala in SALAS:
        start = documentos_previos_por_sala.get(sala, 0) * 2
        while len(documentos) < max_documentos:
            resultados = _buscar_pagina(sesion, sala, start)
            if not resultados:
                break

            for item in resultados:
                if len(documentos) >= max_documentos:
                    break
                ruta = item.get("onlinePath") or ""
                clave = ruta.rsplit(".", 1)[0]  # dedupe .pdf / .docx del mismo fallo
                if not ruta or clave in vistos:
                    continue
                vistos.add(clave)

                texto = _texto_completo(sesion, ruta, sala)
                time.sleep(pausa_segundos)
                if not texto or len(texto) < 100:
                    continue

                titulo = item.get("title", ruta)
                identificador = _identificador_desde_titulo(titulo)
                documentos.append(
                    Documento(
                        id=f"corte_suprema:{sala.lower()}:{identificador}",
                        fuente="corte_suprema",
                        tipo="sentencia",
                        identificador=identificador,
                        titulo=f"Corte Suprema - Sala {sala} - {titulo}",
                        fecha=None,
                        texto=texto,
                        url_original="https://consultaprovidencias.cortesuprema.gov.co/busqueda",
                        metadata={"sala": sala, "magistrado": item.get("doctor"), "ruta": ruta},
                    )
                )

            start += TAMANIO_PAGINA
            if al_guardar is not None:
                al_guardar(documentos)

        if len(documentos) >= max_documentos:
            break

    return documentos
