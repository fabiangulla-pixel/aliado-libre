"""Ingester de los conceptos de la Superintendencia de Servicios Públicos Domiciliarios.

La compilación (normograma.superservicios.gov.co) es el mismo sistema de Avance
Jurídico que la DIAN: páginas estáticas, cada documento en `docs/*.htm` con el
texto dentro de `<div class="panel-documento">`. Los conceptos se listan por año
en `<PAGINA>_<año>.html` (la página sin año es la del año más reciente).

Por qué importa: las preguntas sobre luz, agua y gas («me cortaron la luz», «me
cobraron de más en el recibo») son de las más frecuentes entre las consultas
reales, y la Ley 142 de 1994 sola no las responde: la doctrina de Superservicios
dice cómo se aplica (~600 conceptos por año desde finales de los noventa).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable

import requests
from bs4 import BeautifulSoup

from ingest.anonimizar import enmascarar_destinatario
from ingest.normalizar import fecha_es_a_iso, fix_mojibake
from ingest.schema import Documento

BASE = "https://normograma.superservicios.gov.co/NORMOGRAMA/compilacion/"
PAGINA = "c-dcsdspd_superintendencia_servicios_publicos_domiciliarios_conceptos_orden_cronologico"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
_RUTA = re.compile(r"docs/concepto_[a-z]+_\d+_\d{4}\.htm")


def listar_anio(
    sesion: requests.Session, anio: int | None, base: str = BASE, pagina: str = PAGINA
) -> list[str]:
    """Rutas `docs/...htm` de los conceptos de un año (None = la página por defecto)."""
    sufijo = f"_{anio}" if anio else ""
    r = sesion.get(f"{base}{pagina}{sufijo}.html", verify=False, timeout=60)
    if r.status_code != 200:
        return []
    return sorted(set(_RUTA.findall(r.text)))


def extraer(
    sesion: requests.Session, ruta: str, base: str = BASE, fuente: str = "superservicios"
) -> Documento | None:
    url = base + ruta
    r = sesion.get(url, verify=False, timeout=60)
    if r.status_code != 200:
        return None
    sopa = BeautifulSoup(fix_mojibake(r.content.decode("iso-8859-1", errors="replace")), "html.parser")
    contenedor = sopa.select_one(".panel-documento") or sopa.body
    if contenedor is None:
        return None
    texto = enmascarar_destinatario(contenedor.get_text("\n", strip=True))
    if len(texto) < 80:
        return None
    titulo_tag = sopa.select_one(".titulo-documento")
    identificador = ruta.removeprefix("docs/").removesuffix(".htm")
    m = re.match(r"concepto_[a-z]+_0*(\d+)_(\d{4})", identificador)
    titulo = titulo_tag.get_text(" ", strip=True) if titulo_tag else ""
    if not titulo and m:
        titulo = f"Concepto {m.group(1)} de {m.group(2)}"
    m_fecha = re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", texto)
    fecha = fecha_es_a_iso(m_fecha.group(0)) if m_fecha else None
    if fecha is None and (m_num := re.search(r"Fecha:\s*(\d{2})-(\d{2})-(\d{4})", texto)):
        fecha = f"{m_num.group(3)}-{m_num.group(2)}-{m_num.group(1)}"
    return Documento(
        id=f"{fuente}:{identificador}",
        fuente=fuente,
        tipo="concepto",
        identificador=identificador,
        titulo=titulo or identificador,
        fecha=fecha,
        texto=texto,
        url_original=url,
        metadata={},
    )


def crawl(
    anios: list[int],
    pausa_segundos: float = 0.5,
    documentos_previos: list[Documento] | None = None,
    al_guardar: Callable[[list[Documento]], None] | None = None,
    cada: int = 50,
    base: str = BASE,
    paginas: tuple[str, ...] = (PAGINA,),
    fuente: str = "superservicios",
) -> list[Documento]:
    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    documentos = list(documentos_previos or [])
    vistos = {d.id for d in documentos}
    nuevos = 0
    for anio in anios:
        rutas = sorted({r for p in paginas for r in listar_anio(sesion, anio, base, p)})
        pendientes = [r for r in rutas if f"{fuente}:{r[5:-4]}" not in vistos]
        print(f"{anio}: {len(rutas)} conceptos, {len(pendientes)} pendientes", flush=True)
        for ruta in pendientes:
            try:
                doc = extraer(sesion, ruta, base, fuente)
            except requests.RequestException:
                doc = None
                time.sleep(pausa_segundos * 5)
            if doc is not None:
                documentos.append(doc)
                vistos.add(doc.id)
                nuevos += 1
                if al_guardar is not None and nuevos % cada == 0:
                    al_guardar(documentos)
            time.sleep(pausa_segundos)
        if al_guardar is not None:
            al_guardar(documentos)
    return documentos
