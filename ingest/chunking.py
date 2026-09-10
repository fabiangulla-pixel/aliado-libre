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

# Secciones ceremoniales a excluir (al final del documento)
PATRON_CIERRE = re.compile(
    r"(COMUNÍQUESE\s+Y\s+CÚMPLASE|Comuníquese\s+y\s+Cúmplase|"
    r"DADO\s+EN|Dado\s+en|"
    r"FIRMA|Firma|"
    r"MINISTRO|Ministro|"
    r"PRESIDENTE|Presidente|"
    r"CONGRESO|Congreso).*$",
    re.MULTILINE | re.IGNORECASE | re.DOTALL
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
    """Remueve secciones ceremoniales del final del documento."""
    # Busca el primer match de cierre y elimina TODO lo que sigue
    match = PATRON_CIERRE.search(texto)
    if match:
        return texto[:match.start()].strip()
    return texto.strip()


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

    # Paso 4: Crear fragmentos, filtrando muy pequeños
    fragmentos = []
    for i, texto in enumerate(trozos_articulo):
        texto = texto.strip()
        # Descartar fragmentos triviales (ceremonial que se coló)
        if len(texto) < TAMANIO_MIN:
            continue
        if any(palabra in texto.upper() for palabra in ["COMUNÍQUESE", "DADO EN", "FIRMA"]):
            continue

        fragmentos.append(
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
        )

    return fragmentos
