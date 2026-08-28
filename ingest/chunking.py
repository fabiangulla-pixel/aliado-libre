"""Divide el texto de un Documento en fragmentos indexables.

Prioriza cortar por límites de artículo (unidad citable en derecho colombiano);
si el documento no tiene esa estructura, cae a un corte por tamaño con solape.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ingest.schema import Documento

PATRON_ARTICULO = re.compile(r"(?=^\s*ART[IÍ]CULO\s+\d+[oO°.]?)", re.MULTILINE | re.IGNORECASE)

TAMANIO_MAX = 1500
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


def _cortar_por_tamanio(texto: str) -> list[str]:
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
    trozos_articulo = PATRON_ARTICULO.split(doc.texto)
    trozos_articulo = [t for t in trozos_articulo if t.strip()]

    if len(trozos_articulo) <= 1:
        trozos_articulo = _cortar_por_tamanio(doc.texto)
    else:
        expandidos = []
        for t in trozos_articulo:
            expandidos.extend(_cortar_por_tamanio(t))
        trozos_articulo = expandidos

    return [
        Fragmento(
            id=f"{doc.id}::frag{i}",
            documento_id=doc.id,
            fuente=doc.fuente,
            identificador_documento=doc.identificador,
            titulo_documento=doc.titulo,
            texto=texto.strip(),
            url_original=doc.url_original,
            orden=i,
        )
        for i, texto in enumerate(trozos_articulo)
        if texto.strip()
    ]
