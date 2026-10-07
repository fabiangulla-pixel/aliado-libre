"""Enmascara los datos de quien consultó en conceptos de entidades.

Los conceptos de Superservicios y Supersalud se publican como cartas: después
del saludo («Señora») vienen el nombre, la dirección, la ciudad y a veces el
correo de quien preguntó, hasta la referencia («Ref.: Su solicitud de
concepto»). Las entidades enmascaran los recientes (XXXXXXX) pero no los
antiguos. Ese bloque no aporta nada a la búsqueda y el índice es público: se
sustituye por una marca. Lo mismo con correos y teléfonos sueltos en el texto.

Regla, sin modelo: solo se toca el bloque entre un saludo de línea propia y la
línea de referencia, con un tope de líneas para no comerse el cuerpo si el
documento no trae referencia.
"""

from __future__ import annotations

import re

MARCA_DESTINATARIO = "[Destinatario omitido]"
MARCA_CORREO = "[correo omitido]"
MARCA_TELEFONO = "[teléfono omitido]"
MAX_LINEAS_BLOQUE = 10

_SALUDO = re.compile(
    r"^\s*(se[ñn]or(?:a|es|as)?|doctor(?:a)?|dra?\.|ingenier[oa]|apreciad[oa])\s*:?\s*(?:\((?:a|as|es)\))?\s*:?\s*$",
    re.I,
)
# «Respetada señora Jannet:» — el vocativo repite el nombre que el bloque ya quitó.
_VOCATIVO = re.compile(
    r"^(\s*(?:respetad|apreciad|estimad)\w*\s+(?:se[ñn]or|doctor|ingenier)\w*(?:\s*\(\w+\))?)\s+[^:\n]{1,60}:",
    re.I | re.M,
)
_FIN_BLOQUE = re.compile(
    r"^\s*(ref\b|ref\.|referencia|asunto|radicado|respetad[oa]|apreciad[oa]|cordial|estimad[oa]|"
    r"en atenci[oó]n|de manera atenta|me permito|consulta\b|tema\b)",
    re.I,
)
_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TELEFONO = re.compile(
    r"\b(?:tel[eé]fono|tel\.?|cel(?:ular)?\.?|m[oó]vil|fax)\s*(?:no\.?|n[uú]mero)?\s*:?\s*[\d\s().-]{7,20}\d",
    re.I,
)


def enmascarar_destinatario(texto: str) -> str:
    lineas = texto.split("\n")
    salida: list[str] = []
    i = 0
    while i < len(lineas):
        salida.append(lineas[i])
        if _SALUDO.match(lineas[i]):
            fin = next(
                (
                    j
                    for j in range(i + 1, min(i + 1 + MAX_LINEAS_BLOQUE, len(lineas)))
                    if _FIN_BLOQUE.match(lineas[j])
                ),
                None,
            )
            if fin is not None and fin > i + 1:
                salida.append(MARCA_DESTINATARIO)
                i = fin
                continue
        i += 1
    texto = "\n".join(salida)
    texto = _VOCATIVO.sub(r"\1:", texto)
    texto = _CORREO.sub(MARCA_CORREO, texto)
    return _TELEFONO.sub(MARCA_TELEFONO, texto)
