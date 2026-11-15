"""Ingester del Consejo de Estado — relatoría (servicios.consejodeestado.gov.co).

El buscador (JSF/PrimeFaces en /WebRelatoria/ce/index.xhtml) responde a
peticiones normales, a diferencia del dominio jurisprudencia.ramajudicial.gov.co
que lo servía antes tras un WAF. Pero no hace falta el buscador: cada providencia
se descarga directo por su número de relatoría (NR) en

    /WebRelatoria/FileReferenceServlet?corp=ce&ext=html&file=<NR>

sin sesión. Un NR inexistente responde 200 con cuerpo vacío. Muestreado el
15-nov-2026: hay documentos en 2.000.000-2.025.000 y 2.075.000-2.200.000
(~70-80% de ocupación); por debajo y por encima, vacío. Se recorre el rango.

El HTML (windows-1252) trae primero el resumen de la relatoría —descriptores
en lenguaje llano, muy buenos para recuperar— y luego la providencia con un
encabezado fijo: SECCIÓN, ponente, "Bogotá, D.C., <fecha> (AAAA)",
"Radicación número:", "Actor:", "Demandado:", "Referencia:".
"""

from __future__ import annotations

import html
import re
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

import requests

from ingest.schema import Documento

URL_DOCUMENTO = (
    "https://servicios.consejodeestado.gov.co/WebRelatoria/FileReferenceServlet?corp=ce&ext=html&file={nr}"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
RANGOS = ((2_000_000, 2_030_000), (2_070_000, 2_215_000))
TEXTO_MINIMO = 500


def _limpiar(crudo: str) -> str:
    sin_bloques = re.sub(r"<style.*?</style>|<script.*?</script>|<!--.*?-->", " ", crudo, flags=re.S | re.I)
    # Los saltos del fuente parten párrafos a la mitad: los únicos que valen son las etiquetas de bloque.
    sin_bloques = re.sub(r"\s+", " ", sin_bloques)
    con_saltos = re.sub(r"<\s*(?:br|/p|/div|/h\d|/li|/tr)\b[^>]*>", "\n", sin_bloques, flags=re.I)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", con_saltos))
    lineas = (re.sub(r"[ \t\xa0]+", " ", linea).strip() for linea in texto.splitlines())
    return "\n".join(linea for linea in lineas if linea)


def _campo(patron: str, texto: str) -> str | None:
    m = re.search(patron, texto, flags=re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip(" .:") if m else None


def a_documento(nr: int, crudo: str) -> Documento | None:
    texto = _limpiar(crudo)
    if len(texto) < TEXTO_MINIMO or "CONSEJO DE ESTADO" not in texto.upper():
        return None
    seccion = _campo(
        r"(SECCI[OÓ]N\s+(?:PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA)|SALA DE CONSULTA Y SERVICIO CIVIL"
        r"|SALA PLENA[^\n]{0,60})",
        texto,
    )
    anio = _campo(r"Bogot[aá][^\n]{0,140}?\((\d{4})\)", texto)
    radicado = _campo(r"Radicaci[oó]n\s+n[uú]mero\s*:?\s*([^\n]{5,80})", texto)
    referencia = _campo(
        r"(?:Referencia|Medio de control|Asunto|Acci[oó]n|Proceso)\s*:\s*([^\n]{3,160})", texto
    )
    ponente = _campo(r"Consejer[oa]\s*ponente\s*:\s*([^\n]{3,80})", texto)
    partes = ["Consejo de Estado"]
    if seccion:
        partes.append(seccion.title())
    if referencia:
        partes.append(referencia.capitalize())
    if radicado:
        partes.append(f"Rad. {radicado}")
    return Documento(
        id=f"consejo_estado:{nr}",
        fuente="consejo_estado",
        tipo="sentencia",
        identificador=radicado or str(nr),
        titulo=" - ".join(partes)[:300],
        fecha=anio,
        texto=texto,
        url_original=URL_DOCUMENTO.format(nr=nr),
        metadata={"nr": nr, "seccion": seccion, "ponente": ponente, "referencia": referencia},
    )


def _descargar(sesion: requests.Session, nr: int, intentos: int = 3) -> str | None:
    for intento in range(intentos):
        try:
            r = sesion.get(URL_DOCUMENTO.format(nr=nr), timeout=60, verify=False)
            if r.status_code == 200:
                return r.content.decode("cp1252", errors="replace") if r.content else None
        except requests.exceptions.RequestException:
            pass
        time.sleep(2 * (intento + 1))
    raise ConnectionError(f"NR {nr}: sin respuesta tras {intentos} intentos")


def numeros(rangos: Iterable[tuple[int, int]], desde: int = 0) -> list[int]:
    return [nr for ini, fin in rangos for nr in range(max(ini, desde), fin)]


def crawl(
    max_documentos: int = 500,
    pausa_segundos: float = 0.1,
    al_guardar: Callable | None = None,
    documentos_previos: list[Documento] | None = None,
    rangos: Iterable[tuple[int, int]] = RANGOS,
    desde_nr: int = 0,
    al_avanzar: Callable[[int], None] | None = None,
    hilos: int = 4,
    lote: int = 200,
) -> list[Documento]:
    """Recorre los NR de `rangos` desde `desde_nr`, en lotes con `hilos`
    descargas simultáneas. `al_avanzar(nr)` recibe el último NR de cada lote
    ya procesado entero, para reanudar sin repetir."""
    documentos = list(documentos_previos or [])
    vistos = {d.id for d in documentos}
    pendientes = numeros(rangos, desde_nr)
    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        for i in range(0, len(pendientes), lote):
            if len(documentos) >= max_documentos:
                break
            bloque = [nr for nr in pendientes[i : i + lote] if f"consejo_estado:{nr}" not in vistos]
            for nr, crudo in zip(bloque, pool.map(lambda n: _descargar(sesion, n), bloque), strict=True):
                doc = a_documento(nr, crudo) if crudo else None
                if doc is not None and len(documentos) < max_documentos:
                    documentos.append(doc)
                    vistos.add(doc.id)
            if al_guardar is not None:
                al_guardar(documentos)
            if al_avanzar is not None and len(documentos) < max_documentos:
                al_avanzar(pendientes[min(i + lote, len(pendientes)) - 1])
            time.sleep(pausa_segundos)
    return documentos
