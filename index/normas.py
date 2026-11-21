"""Reconocer que norma es un documento o cual nombra un texto.

Una sola definicion para el programa (index/buscar.py, enrutador de norma) y
para la medicion (finetune/eval/acierto.py): si divergieran, se mediria una
cosa y se desplegaria otra.

La norma se representa como (tipo, numero, anio): ("ley", 1480, "2011"),
("dec", 2663, "1950"). Los codigos se reconocen tambien por su nombre.
"""

from __future__ import annotations

import re

Norma = tuple[str, int, str]

_PATRON = re.compile(
    r"(ley|decreto|resoluci[oó]n|acto[-_ ]legislativo|circular)[-_ ]+"
    r"(?:no\.?[-_ ]*)?(\d+)[-_ ]+(?:de[-_ ]+)?(\d{4})",
    re.IGNORECASE,
)

# Los codigos se citan por su nombre, no por numero ("Codigo de Comercio,
# articulo 1058").
_CODIGOS = [
    (r"c[oó]digo\s+de\s+comercio", ("dec", 410, "1971")),
    (r"c[oó]digo\s+sustantivo\s+del\s+trabajo", ("dec", 2663, "1950")),
    (r"estatuto\s+tributario", ("dec", 624, "1989")),
    (r"c[oó]digo\s+general\s+del\s+proceso", ("ley", 1564, "2012")),
    (r"c[oó]digo\s+de\s+procedimiento\s+penal", ("ley", 906, "2004")),
    (r"c[oó]digo\s+penal", ("ley", 599, "2000")),
    (r"c[oó]digo\s+civil", ("ley", 84, "1873")),
    (r"estatuto\s+del\s+consumidor", ("ley", 1480, "2011")),
    (r"c[oó]digo\s+de\s+(la\s+)?infancia", ("ley", 1098, "2006")),
    (r"c[oó]digo\s+(nacional\s+)?de\s+polic[ií]a", ("ley", 1801, "2016")),
    (r"c[oó]digo\s+nacional\s+de\s+tr[aá]nsito", ("ley", 769, "2002")),
    (r"\bcpaca\b|c[oó]digo\s+de\s+procedimiento\s+administrativo", ("ley", 1437, "2011")),
]
_CODIGOS = [(re.compile(p, re.IGNORECASE), n) for p, n in _CODIGOS]


def _hallazgos(t: str) -> list[tuple[int, Norma]]:
    salida = []
    m = _PATRON.search(t)
    if m:
        tipo = m.group(1).lower().replace("ó", "o")[:3]
        salida.append((m.start(), (tipo, int(m.group(2)), m.group(3))))
    for patron, n in _CODIGOS:
        mc = patron.search(t)
        if mc:
            salida.append((mc.start(), n))
    return salida


def norma(*textos: str | None) -> Norma | None:
    """La primera norma que nombra el texto (por numero o por nombre), o None."""
    for t in textos:
        if t:
            h = _hallazgos(t)
            if h:
                return min(h)[1]
    return None


def norma_de_resultado(r: dict) -> Norma | None:
    """Que norma ES este documento (no cual menciona).

    El id es lo mas fiable (legalize_co_github:LEY-1480-2011). El titulo solo
    cuenta si EMPIEZA por la norma ("Ley 142 de 1994 - Gestor Normativo"): un
    oficio titulado "...sobre el articulo 51 de la Ley 1480 de 2011" habla de
    la ley, no es la ley.
    """
    doc = r.get("documento_id", "") or ""
    por_id = norma(doc.split(":", 1)[-1].replace("_", "-"))
    if por_id:
        return por_id
    titulo = (r.get("titulo_documento") or "")[:120].lstrip()
    h = _hallazgos(titulo)
    inicio = [n for pos, n in h if pos == 0]
    return inicio[0] if inicio else None
