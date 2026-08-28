"""Utilidades de normalización compartidas entre ingesters."""

from __future__ import annotations

import re

MESES = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}
PATRON_FECHA_ES = re.compile(r"(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\s+de\s+(\d{4})", re.IGNORECASE)


def fix_mojibake(texto: str) -> str:
    """Revierte texto UTF-8 doblemente codificado ("producciÃ³n" -> "producción").
    Corrige a nivel de palabra: un byte roto en un punto del texto no debe
    impedir corregir el resto (una sola línea/palabra puede fallar el
    re-decode sin que el documento entero se quede sin corregir)."""
    try:
        return texto.encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    partes = re.split(r"(\s+)", texto)
    corregidas = []
    for parte in partes:
        try:
            corregidas.append(parte.encode("latin1").decode("utf-8"))
        except (UnicodeDecodeError, UnicodeEncodeError):
            corregidas.append(parte)
    return "".join(corregidas)


def fecha_es_a_iso(texto_fecha: str | None) -> str | None:
    """Convierte "26 de mayo de 2015" -> "2015-05-26". Si no matchea el
    patrón esperado, devuelve el texto original tal cual (no se pierde
    información, solo no se normaliza)."""
    if not texto_fecha:
        return texto_fecha
    m = PATRON_FECHA_ES.search(texto_fecha)
    if not m:
        return texto_fecha
    dia, mes_texto, anio = m.groups()
    mes = MESES[mes_texto.lower()]
    return f"{anio}-{mes}-{int(dia):02d}"
