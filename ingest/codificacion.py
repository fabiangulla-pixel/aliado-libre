"""Repara texto con doble codificación UTF-8 («ARTÃ\\x8dCULO» -> «ARTÍCULO»).

Medido el 3-oct-2026: 28.373 fragmentos de 64 documentos del Gestor Normativo
(entre ellos el Código de Comercio) y unos cientos de otras fuentes llegaron al
índice así. El portal anuncia UTF-8 en la cabecera e ISO-8859-1 en el HTML, y
algunas normas ya están dañadas en origen. El daño no se ve en una búsqueda
normal: el FTS no encuentra «artículo» en «artÃ­culo» y el embedding codifica
basura, así que esas normas simplemente aparecen menos.

`ftfy` solo toca secuencias que son mojibake reconocible; el texto sano sale
idéntico (comprobado con tildes, eñes, comillas angulares y rayas).
"""

from __future__ import annotations

import re

_MARCAS = re.compile(r"[ÃÂ][\x80-\xbf\u0080-ÿ‘-›ŒœŠšŸŽžƒ]")
# Resto típico de un espacio duro (C2 A0) mal decodificado que ftfy deja suelto.
_A_SUELTA = re.compile(r"Â(?=\s)")


def tiene_mojibake(texto: str) -> bool:
    return bool(texto) and bool(_MARCAS.search(texto))


def reparar(texto: str) -> str:
    """Devuelve el texto reparado; si no hay mojibake, el mismo objeto."""
    if not tiene_mojibake(texto):
        return texto
    import ftfy

    arreglado = ftfy.fix_text(texto, normalization="NFC", uncurl_quotes=False, fix_line_breaks=False)
    return _A_SUELTA.sub("", arreglado)
