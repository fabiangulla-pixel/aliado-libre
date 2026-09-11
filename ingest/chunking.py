"""Divide el texto de un Documento en fragmentos indexables.

Estrategia mejorada:
1. Detecta estructura del documento (decreto, sentencia, ley)
2. Elimina secciones ceremoniales (Comuníquese y Cúmplase, firmas, fechas)
3. Prioriza cortar por límites de artículo (unidad citable en derecho colombiano)
4. Dentro de un artículo: respeta párrafos cuando sea posible
5. Fallback: corte por tamaño con solape inteligente
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingest.schema import Documento

PATRON_ARTICULO = re.compile(r"(?=^\s*ART[IÍ]CULO\s+\d+[oO°.]?)", re.MULTILINE | re.IGNORECASE)
PATRON_PARRAFO = re.compile(r"\n\s*\n+")

# Fórmulas de cierre: solo las que en derecho colombiano cierran el acto, y solo
# como frase completa al principio de una línea. La versión anterior cortaba por
# FIRMA/MINISTRO/PRESIDENTE sueltos, sin límites de palabra ni ancla: "confirma"
# y "firmará" disparaban el corte y se llevaban por delante el resto del
# documento. Medido sobre el corpus real: se perdía el 77% de los caracteres.
PATRON_CIERRE = re.compile(
    r"^[ 	]*(?:COMUN[IÍ]QUESE|PUBL[IÍ]QUESE|NOT[IÍ]F[IÍ]QUESE|C[UÚ]MPLASE)"
    r"(?:[ 	,]+(?:Y|E)?[ 	,]*(?:PUBL[IÍ]QUESE|NOT[IÍ]F[IÍ]QUESE|C[UÚ]MPLASE|EJEC[UÚ]TESE))*"
    r"[ 	]*[.…]?[ 	]*$"
    r"|^[ 	]*DADO\s+EN.{0,120}?a\s+los",
    re.MULTILINE | re.IGNORECASE,
)

# Un cierre solo es un cierre si está al final. Si el patrón aparece antes de
# esta fracción del documento, es una cita dentro del cuerpo, no el cierre.
FRACCION_MINIMA_DEL_CIERRE = 0.7

# Un trozo corto que no es más que la fórmula, la fecha o la firma.
PATRON_SOLO_CEREMONIAL = re.compile(
    r"[\s.,;:—-]*(?:(?:COMUN[IÍ]QUESE|PUBL[IÍ]QUESE|NOT[IÍ]F[IÍ]QUESE|C[UÚ]MPLASE|EJEC[UÚ]TESE|"
    r"DADO\s+EN|FIRMADO|EL\s+PRESIDENTE|EL\s+MINISTRO)\b[^\n]*[\s.,;:]*)+",
    re.IGNORECASE,
)

TAMANIO_MAX = 1500
TAMANIO_MIN = 150
SOLAPE = 200


@dataclass
class Fragmento:
    id: str
    documento_id: str
    fuente: str
    identificador_documento: str
    titulo_documento: str
    texto: str
    url_original: str
    orden: int


def _limpiar_ceremonial(texto: str) -> str:
    """Remueve la fórmula de cierre y lo que la sigue, si de verdad está al final.

    Nunca devuelve vacío: si el corte se comiera el documento entero, es señal de
    que el patrón acertó donde no debía y se conserva el texto original.
    """
    texto = texto.strip()
    if not texto:
        return texto
    for match in PATRON_CIERRE.finditer(texto):
        if match.start() >= len(texto) * FRACCION_MINIMA_DEL_CIERRE:
            recortado = texto[: match.start()].strip()
            return recortado or texto
    return texto


def _cortar_respetando_parrafos(texto: str) -> list[str]:
    """Corta un artículo por párrafos antes de usar tamaño."""
    if len(texto) <= TAMANIO_MAX:
        return [texto]

    # Primero intenta cortar por párrafos
    parrafos = PATRON_PARRAFO.split(texto)
    parrafos = [p.strip() for p in parrafos if p.strip() and len(p.strip()) >= TAMANIO_MIN]

    if len(parrafos) <= 1:
        # Sin párrafos claros: corta por tamaño
        return _cortar_por_tamanio(texto)

    # Agrupa párrafos para no exceder TAMANIO_MAX
    bloques = []
    bloque_actual = ""
    for parrafo in parrafos:
        if len(bloque_actual) + len(parrafo) + 1 <= TAMANIO_MAX:
            bloque_actual += ("\n\n" if bloque_actual else "") + parrafo
        else:
            if bloque_actual:
                bloques.append(bloque_actual)
            bloque_actual = parrafo
    if bloque_actual:
        bloques.append(bloque_actual)

    return bloques if bloques else _cortar_por_tamanio(texto)


def _cortar_por_tamanio(texto: str) -> list[str]:
    """Fallback: corta por tamaño con solape."""
    if len(texto) <= TAMANIO_MAX:
        return [texto]
    partes = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + TAMANIO_MAX, len(texto))
        partes.append(texto[inicio:fin])
        if fin == len(texto):
            break
        inicio = fin - SOLAPE
    return partes


def _es_solo_ceremonial(texto: str) -> bool:
    """Un trozo corto que es solo la fórmula de cierre, la fecha o la firma.

    Se comprueba contra el trozo completo, no por subcadena: el filtro anterior
    descartaba cualquier fragmento que contuviera "FIRMA", y eso incluye
    "confirma", "firmante" o "firmará".
    """
    return bool(PATRON_SOLO_CEREMONIAL.fullmatch(texto.strip()))


def fragmentar(doc: Documento) -> list[Fragmento]:
    # Paso 1: Limpiar secciones ceremoniales
    texto_limpio = _limpiar_ceremonial(doc.texto)

    # Paso 2: Intentar cortar por artículos
    trozos_articulo = PATRON_ARTICULO.split(texto_limpio)
    trozos_articulo = [t.strip() for t in trozos_articulo if t.strip()]

    # Paso 3: Si hay artículos identificables, procesar cada uno
    if len(trozos_articulo) > 1:
        expandidos = []
        for t in trozos_articulo:
            expandidos.extend(_cortar_respetando_parrafos(t))
        trozos_articulo = expandidos
    else:
        # Sin estructura de artículos: cortar respetando párrafos
        trozos_articulo = _cortar_respetando_parrafos(texto_limpio)

    # Paso 4: descartar los trozos que no aportan, pero nunca el documento entero
    utiles = []
    for texto in trozos_articulo:
        texto = texto.strip()
        if len(texto) < TAMANIO_MIN and _es_solo_ceremonial(texto):
            continue
        utiles.append(texto)

    # Un documento corto es un documento corto, no basura: si el filtro se lo
    # llevó todo, se indexa el texto limpio tal cual. Antes, el 12,2% de los
    # documentos del corpus salía con cero fragmentos y desaparecía del índice.
    if not utiles:
        utiles = [texto_limpio.strip()] if texto_limpio.strip() else []

    fragmentos = [
        Fragmento(
            id=f"{doc.id}::frag{i}",
            documento_id=doc.id,
            fuente=doc.fuente,
            identificador_documento=doc.identificador,
            titulo_documento=doc.titulo,
            texto=texto,
            url_original=doc.url_original,
            orden=i,
        )
        for i, texto in enumerate(utiles)
    ]

    return fragmentos
