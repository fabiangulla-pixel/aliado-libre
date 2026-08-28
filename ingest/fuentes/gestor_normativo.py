"""Ingester de Gestor Normativo (Función Pública) — legislación nacional colombiana.

Cada norma vive en https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=<ID>
y trae, además del texto, una sección "Vigencias" con las relaciones normativas
explícitas (modifica/deroga/reglamenta/etc.) hacia otras normas por su propio ID.
Esa sección es oro: nos da el grafo de vigencia normativa sin tener que inferirlo.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from ingest.schema import Documento

BASE = "https://www.funcionpublica.gov.co/eva/gestornormativo"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def _fix_mojibake(texto: str) -> str:
    """El sitio sirve bytes UTF-8 pero declara ISO-8859-1 en el <meta>, lo que
    produce texto doblemente codificado ("producciÃ³n"). Se revierte reinterpretando
    como latin1 y decodificando como utf-8.

    Algunas páginas (contenido legado en su CMS) tienen bytes realmente corruptos
    en algún punto ("ARTÃCULO" en vez de "ARTÃ­CULO") que rompen el re-decode de
    TODO el string si se intenta de una sola vez. Por eso se corrige línea por
    línea: una línea corrupta se deja tal cual, en vez de arrastrar a todo el
    documento a quedar sin corregir."""
    try:
        return texto.encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Por línea tampoco basta: hay líneas de miles de caracteres (un <p> entero
    # en una sola línea) donde un byte corrupto en cualquier punto tumba la
    # corrección de toda la línea. Se baja a nivel de palabra (separando por
    # espacios, preservando los separadores) para que un byte roto solo afecte
    # a esa palabra puntual.
    partes = re.split(r"(\s+)", texto)
    corregidas = []
    for parte in partes:
        try:
            corregidas.append(parte.encode("latin1").decode("utf-8"))
        except (UnicodeDecodeError, UnicodeEncodeError):
            corregidas.append(parte)
    return "".join(corregidas)


@dataclass
class RelacionVigencia:
    tipo: str  # "Modificado por", "Deroga", "Reglamenta parcialmente", etc.
    id_relacionado: str
    descripcion: str


def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    # El gestor normativo exige cookie de sesión establecida antes de servir norma.php
    s.get(f"{BASE}/", verify=False, timeout=20)
    return s


def _parsear_vigencias(soup: BeautifulSoup) -> list[RelacionVigencia]:
    relaciones = []
    contenedor = soup.select_one("#collapseThree .card-body")
    if not contenedor:
        return relaciones
    for a in contenedor.select("a[href*='norma.php?i=']"):
        href = a.get("href", "")
        m = re.search(r"i=(\d+)", href)
        if not m:
            continue
        texto = _fix_mojibake(a.get_text(strip=True))
        # El texto es del tipo "Modificado por Decreto 226 de 2026 ..."
        tipo_match = re.match(
            r"^(Modificado por|Modificado transitoriamente por|Adicionado por|"
            r"Sustituido por|Derogado parcialmente|Derogado por|Deroga parcialmente|"
            r"Deroga|Reglamenta parcialmente|Reglamenta|Adiciona)",
            texto,
        )
        tipo = tipo_match.group(1) if tipo_match else "relacionado"
        relaciones.append(RelacionVigencia(tipo=tipo, id_relacionado=m.group(1), descripcion=texto))
    return relaciones


def _parsear_documento(html_crudo: str, norma_id: str, url: str) -> Documento | None:
    """Parseo puro (sin red) — separado para poder probarse con fixtures."""
    html = _fix_mojibake(html_crudo)
    soup = BeautifulSoup(html, "lxml")

    titulo_tag = soup.title
    titulo = titulo_tag.get_text(strip=True) if titulo_tag else f"Norma {norma_id}"
    # Páginas de índice/categoría no tienen .descripcion-contenido -> se descartan
    contenido_div = soup.select_one(".descripcion-contenido")
    if contenido_div is None:
        return None

    texto = contenido_div.get_text("\n", strip=True)
    if len(texto) < 200:
        return None

    vigencias = _parsear_vigencias(soup)

    fecha_match = re.search(r"Fecha de Expedici[oó]n:\s*([^<\n]+)", html)
    fecha = fecha_match.group(1).strip() if fecha_match else None

    tipo = (
        "decreto"
        if "decreto" in titulo.lower()
        else ("ley" if titulo.lower().startswith("ley") or " ley " in titulo.lower() else "resolucion")
    )

    return Documento(
        id=f"gestor_normativo:{norma_id}",
        fuente="gestor_normativo",
        tipo=tipo,  # type: ignore[arg-type]
        identificador=titulo.split(" - ")[0].strip(),
        titulo=titulo,
        fecha=fecha,
        texto=texto,
        url_original=url,
        metadata={
            "vigencias": [
                {"tipo": v.tipo, "id_relacionado": v.id_relacionado, "descripcion": v.descripcion}
                for v in vigencias
            ]
        },
    )


def obtener_norma(sesion: requests.Session, norma_id: str) -> Documento | None:
    url = f"{BASE}/norma.php?i={norma_id}"
    r = sesion.get(url, verify=False, timeout=30)
    if r.status_code != 200:
        return None
    return _parsear_documento(r.text, norma_id, url)


def crawl(
    ids_semilla: list[str],
    max_documentos: int = 50,
    pausa_segundos: float = 1.0,
    al_guardar=None,
) -> list[Documento]:
    """BFS a partir de IDs semilla, siguiendo los enlaces de la sección Vigencias.
    pausa_segundos por defecto es conservador para no golpear el servidor del Estado.
    Si se pasa `al_guardar(documentos)`, se invoca cada 25 documentos nuevos como
    checkpoint incremental (para no perder el avance si el proceso se interrumpe)."""
    sesion = _sesion()
    vistos: set[str] = set()
    cola = list(ids_semilla)
    documentos: list[Documento] = []

    while cola and len(documentos) < max_documentos:
        norma_id = cola.pop(0)
        if norma_id in vistos:
            continue
        vistos.add(norma_id)

        doc = obtener_norma(sesion, norma_id)
        time.sleep(pausa_segundos)
        if doc is None:
            continue
        documentos.append(doc)

        if al_guardar is not None and len(documentos) % 25 == 0:
            al_guardar(documentos)

        for rel in doc.metadata.get("vigencias", []):
            if rel["id_relacionado"] not in vistos:
                cola.append(rel["id_relacionado"])

    return documentos
