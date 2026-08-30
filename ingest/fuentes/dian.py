"""Ingester de la Compilación Jurídica de la DIAN (normograma.dian.gov.co).

No es SPA: cada materia (tributario/aduanero/cambiario/institucional) tiene una
página estática con "opciones" (normativa/doctrina/jurisprudencia) que, al
desplegarse en el navegador, cargan un fragmento HTML estático
"<pagina>_parte_NN.html" con los enlaces a cada documento en "docs/*.htm" —
descubierto leyendo openClosePanelArbolOpcion_aux.js, no hace falta navegador
para nada de esto. El propio documento HTML trae el texto completo dentro de
un <div class="panel-documento">, con el mismo mojibake (ISO-8859-1 declarado,
UTF-8 real) que Gestor Normativo."""

from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

from ingest.normalizar import fecha_es_a_iso, fix_mojibake
from ingest.schema import Documento

BASE = "https://normograma.dian.gov.co/dian/compilacion/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Página raíz de cada materia + prefijo de las páginas de "opción" (normativa/
# doctrina/jurisprudencia) que cuelgan de ella, según el menú de cada materia.
MATERIAS = {
    "tributario": ["t_1_normativa_tributaria", "t_2_doctrina_tributaria", "t_3_jurisprudencia_tributaria"],
    "aduanero": ["a_1_normativa_aduanera", "a_2_doctrina_aduanera", "a_3_jurisprudencia_aduanera"],
    "cambiario": ["c_1_normativa_cambiaria", "c_2_doctrina_cambiaria", "c_3_jurisprudencia_cambiaria"],
}

TIPO_POR_PREFIJO = {"1": "resolucion", "2": "concepto", "3": "sentencia"}


def _listar_partes(sesion: requests.Session, pagina_opcion: str) -> list[str]:
    """Devuelve las rutas relativas 'docs/*.htm' enlazadas desde todas las
    partes (_parte_01, _parte_02, ...) de una página de opción. Se detiene en
    la primera parte que no exista (404)."""
    rutas: list[str] = []
    n = 1
    while True:
        sufijo = f"_parte_{n:02d}"
        url = f"{BASE}{pagina_opcion}{sufijo}.html"
        r = sesion.get(url, timeout=20)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("docs/") and href.endswith((".htm", ".html")):
                rutas.append(href)
        n += 1
    # cada documento suele aparecer 2 veces (título + fecha enlazan por separado)
    return sorted(set(rutas))


def _extraer_documento(sesion: requests.Session, materia: str, tipo: str, ruta: str) -> Documento | None:
    url = BASE + ruta
    r = sesion.get(url, timeout=20)
    if r.status_code != 200:
        return None

    crudo = r.content.decode("iso-8859-1", errors="replace")
    html_corregido = fix_mojibake(crudo)
    soup = BeautifulSoup(html_corregido, "html.parser")

    contenedor = soup.select_one(".panel-documento") or soup.body
    if contenedor is None:
        return None
    texto = contenedor.get_text("\n", strip=True)
    if len(texto) < 80:
        return None

    titulo_tag = soup.select_one(".titulo-documento") or soup.title
    titulo = titulo_tag.get_text(" ", strip=True) if titulo_tag else ruta

    m_fecha = re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", texto)
    fecha = fecha_es_a_iso(m_fecha.group(0)) if m_fecha else None

    identificador = ruta.removeprefix("docs/").removesuffix(".htm").removesuffix(".html")

    return Documento(
        id=f"dian:{materia}:{identificador}",
        fuente="dian",
        tipo=tipo,
        identificador=identificador,
        titulo=titulo,
        fecha=fecha,
        texto=texto,
        url_original=url,
        metadata={"materia": materia},
    )


def crawl(
    max_documentos: int = 500,
    pausa_segundos: float = 0.5,
    al_guardar=None,
    documentos_previos: list[Documento] | None = None,
) -> list[Documento]:
    """Si se pasa `documentos_previos` (de una corrida anterior), no se
    vuelven a descargar — permite reanudar un crawl interrumpido."""
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    documentos_previos = documentos_previos or []
    documentos: list[Documento] = list(documentos_previos)
    vistos: set[str] = {f"{d.metadata.get('materia')}:docs/{d.identificador}.htm" for d in documentos_previos}

    for materia, paginas_opcion in MATERIAS.items():
        for pagina_opcion in paginas_opcion:
            if len(documentos) >= max_documentos:
                return documentos
            tipo = TIPO_POR_PREFIJO.get(pagina_opcion[2], "concepto")
            rutas = _listar_partes(sesion, pagina_opcion)
            for i, ruta in enumerate(rutas):
                if len(documentos) >= max_documentos:
                    break
                clave = f"{materia}:{ruta}"
                if clave in vistos:
                    continue
                vistos.add(clave)
                doc = _extraer_documento(sesion, materia, tipo, ruta)
                if doc is not None:
                    documentos.append(doc)
                time.sleep(pausa_segundos)
                # algunas opciones (ej. normativa tributaria) traen miles de
                # documentos — sin este checkpoint intermedio, una corrida
                # interrumpida a mitad de camino perdería todo el progreso
                if al_guardar is not None and i % 50 == 0:
                    al_guardar(documentos)
            if al_guardar is not None:
                al_guardar(documentos)

    return documentos
