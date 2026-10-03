"""Reconoce citas normativas colombianas: «art. 64 del CST», «T-760/08», «Ley 1480 de 2011».

Por qué existe: la búsqueda híbrida es buena con lenguaje llano y mala con
números exactos. «Ley 100» y «Ley 1000» se parecen para un embedding, y el FTS
une los términos. Una cita tipo+número+año identifica UNA norma, así que vale
la pena reconocerla y saltarse la búsqueda.

Portado a Python desde Normativa-colombiana-MCP (src/nucleo/citas.ts y
src/nucleo/codigos.ts), © 2026 Angel Peña, licencia MIT:
https://github.com/Angelthebestone/Normativa-colombiana-MCP
Las decisiones de diseño (precedencia entre código y ley citados, año ambiguo,
radicados de origen vs. de alta corte) son suyas y están medidas allí.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from dataclasses import dataclass


def sin_tildes(s: str) -> str:
    """Quita tildes carácter a carácter: los índices del original se conservan."""
    return "".join(unicodedata.normalize("NFD", c)[0] for c in s)


def _normaliza(s: str) -> str:
    return sin_tildes(s).lower().strip()


@dataclass(frozen=True)
class Codigo:
    nombre: str
    tipo: str
    numero: str
    anio: str
    alias: tuple[str, ...]


# Los diez códigos que concentran el litigio. "CP" queda fuera (Código Penal y
# Constitución Política) y "C.C." también (es la cédula de ciudadanía).
CODIGOS: tuple[Codigo, ...] = (
    Codigo("Código Civil", "ley", "84", "1873", ("codigo civil", "codigo civil colombiano", "c. civil")),
    Codigo(
        "Código de Comercio",
        "decreto",
        "410",
        "1971",
        ("codigo de comercio", "codigo del comercio", "c. de co."),
    ),
    Codigo(
        "Código Sustantivo del Trabajo",
        "decreto",
        "2663",
        "1950",
        ("codigo sustantivo del trabajo", "codigo sustantivo de trabajo", "cst"),
    ),
    Codigo(
        "Código Procesal del Trabajo y de la Seguridad Social",
        "decreto",
        "2158",
        "1948",
        (
            "codigo procesal del trabajo y de la seguridad social",
            "codigo procesal del trabajo",
            "codigo de procedimiento laboral",
            "cpts",
            "cpt",
        ),
    ),
    Codigo("Código Penal", "ley", "599", "2000", ("codigo penal",)),
    Codigo("Código de Procedimiento Penal", "ley", "906", "2004", ("codigo de procedimiento penal", "cpp")),
    Codigo("Código General del Proceso", "ley", "1564", "2012", ("codigo general del proceso", "cgp")),
    Codigo(
        "Código de Procedimiento Administrativo y de lo Contencioso Administrativo",
        "ley",
        "1437",
        "2011",
        ("codigo de procedimiento administrativo y de lo contencioso administrativo", "cpaca"),
    ),
    Codigo(
        "Código de la Infancia y la Adolescencia",
        "ley",
        "1098",
        "2006",
        ("codigo de la infancia y la adolescencia", "codigo de infancia y adolescencia"),
    ),
    Codigo("Estatuto Tributario", "decreto", "624", "1989", ("estatuto tributario",)),
)

# De más largo a más corto: "código de procedimiento penal" gana a "código penal".
_RE_ALIAS = re.compile(
    r"\b("
    + "|".join(re.escape(a) for a in sorted((a for c in CODIGOS for a in c.alias), key=len, reverse=True))
    + r")(?![\wáéíóúñ])",
    re.I,
)
_POR_ALIAS = {a: c for c in CODIGOS for a in c.alias}


def codigo_citado(texto: str) -> tuple[Codigo, int] | None:
    """Primer código nombrado y su posición en el texto."""
    m = _RE_ALIAS.search(sin_tildes(texto).lower())
    if not m:
        return None
    c = _POR_ALIAS.get(m.group(1).lower())
    return (c, m.start()) if c else None


@dataclass(frozen=True)
class Cita:
    tipo: str
    numero: str
    anio: str | None = None
    articulo: str | None = None
    sentencia: str | None = None  # forma canónica: C-337/11, T-099/24, SU-123/20
    codigo: str | None = None  # nombre del código si la cita llegó por su nombre


_NOMBRES_TIPO = (
    r"acto legislativo|circular conjunta|circular externa|circular unificada|constituci[oó]n pol[ií]tica|"
    r"concepto marco|criterio unificado|decreto ley|documento conpes|acuerdo|auto|circular|concepto|decreto|"
    r"directiva|estatutos|ley|reglamento|resoluci[oó]n|sentencia"
)

# El guion es parte del número en el Estatuto Tributario ("art. 771-5").
_RE_ARTICULO = re.compile(r"\bart(?:[íi]culo|\.)?\s*(\d+(?:[.-]\d+)*[A-Za-z]?)", re.I)
# "C-337/11", "C-351 de 2013", "T-099-24".
_RE_SENTENCIA = re.compile(r"\b(C|T|SU|A)(\s*[.-]\s*|\s*)(\d{1,4})\s*(?:[/-]|\s+de\s+)\s*(\d{2,4})\b", re.I)
# Sin guion ni punto ("a 3/4", "a 15 de 2023") la letra suelta es casi siempre
# prosa de quien pregunta, no una providencia: entonces se exige la palabra antes.
_RE_PALABRA_SENTENCIA = re.compile(r"\b(sentencia|auto|providencia)\s*$", re.I)
# El número se toma entero: con un tope de dígitos "Ley 99999999 de 1800" se partía.
_RE_TIPO_NUM = re.compile(
    rf"\b({_NOMBRES_TIPO})\s*(?:n[ºo°.]?\s*)?(\d+)(?:\s*(?:de|del|/)\s*(\d{{4}}|\d{{2}}))?", re.I
)
# Exige «ción»: no casa con «Constitucional» (Corte) ni con «inconstitucional».
_RE_CONSTITUCION = re.compile(r"\bconstituci[oó]n\b", re.I)


def _expandir_anio(yy: str) -> str:
    """92 -> 1992, 24 -> 2024."""
    n = int(yy)
    return str(1900 + n if n >= 50 else 2000 + n)


def parsear_cita(texto: str) -> Cita | None:
    """La cita normativa del texto, o None si no la hay."""
    m_art = _RE_ARTICULO.search(texto)
    art = m_art.group(1) if m_art else None

    s = next(
        (
            x
            for x in _RE_SENTENCIA.finditer(texto)
            if x.group(2).strip() or _RE_PALABRA_SENTENCIA.search(texto[: x.start()])
        ),
        None,
    )
    if s:
        letra, num, a = s.group(1).upper(), s.group(3), s.group(4)
        anio = a if len(a) == 4 else _expandir_anio(a)
        return Cita(
            tipo="auto" if letra == "A" else "sentencia",
            numero=num,
            anio=anio,
            articulo=art,
            sentencia=f"{letra}-{num.zfill(3)}/{anio[-2:]}",
        )

    m = _RE_TIPO_NUM.search(texto)
    # "art. 217 del Código Civil, modificado por la Ley 1060 de 2006" cita el
    # Código; "art. 5 de la Ley 1060 de 2006, que modifica el Código Civil" cita
    # la ley: gana la referencia que aparece ANTES.
    cod = codigo_citado(texto)
    con = _RE_CONSTITUCION.search(texto)
    infinito = 10**9
    if con and con.start() < (cod[1] if cod else infinito) and con.start() < (m.start() if m else infinito):
        return Cita("constitucion politica", "1", "1991", art)
    if cod and (not m or cod[1] < m.start()):
        c = cod[0]
        return Cita(c.tipo, c.numero, c.anio, art, codigo=c.nombre)
    if not m:
        return None
    anio_bruto = m.group(3)
    return Cita(
        tipo=_normaliza(m.group(1)),
        numero=str(int(m.group(2))),
        anio=(anio_bruto if len(anio_bruto) == 4 else _expandir_anio(anio_bruto)) if anio_bruto else None,
        articulo=art,
    )


# --- Radicado judicial único de 23 dígitos ---------------------------------

_DEPARTAMENTOS = {
    "05": "Antioquia", "08": "Atlántico", "11": "Bogotá D.C.", "13": "Bolívar", "15": "Boyacá",
    "17": "Caldas", "18": "Caquetá", "19": "Cauca", "20": "Cesar", "23": "Córdoba",
    "25": "Cundinamarca", "27": "Chocó", "41": "Huila", "44": "La Guajira", "47": "Magdalena",
    "50": "Meta", "52": "Nariño", "54": "Norte de Santander", "63": "Quindío", "66": "Risaralda",
    "68": "Santander", "70": "Sucre", "73": "Tolima", "76": "Valle del Cauca", "81": "Arauca",
    "85": "Casanare", "86": "Putumayo",
    "88": "Archipiélago de San Andrés, Providencia y Santa Catalina",
    "91": "Amazonas", "94": "Guainía", "95": "Guaviare", "97": "Vaupés", "99": "Vichada",
}  # fmt: skip

# Solo prefijos que por sí mismos identifican una alta corte: un radicado que
# asoma en una sentencia suele ser el del juzgado de ORIGEN, no el de la corte.
_POR_PREFIJO = {
    "0315": ("consejo-de-estado", ""),
    "0325": ("consejo-de-estado", "Sección Segunda (Subsección B)"),
    "0328": ("consejo-de-estado", "Sección Quinta"),
    "0203": ("corte-suprema", "Sala de Casación Civil"),
}

_RE_RADICADO = re.compile(
    r"(?<!\d)(\d{5})[\s-]*(\d{2})[\s-]*(\d{2})[\s-]*(\d{3})[\s-]*(\d{4})[\s-]*(\d{5})[\s-]*(\d{2})\s*(?:\(AC\))?(?!\d)",
    re.I,
)


@dataclass(frozen=True)
class Radicado:
    radicado: str
    formateado: str
    departamento: str
    anio: str
    corporacion: str  # consejo-de-estado | corte-suprema | desconocida
    etiqueta: str


def parsear_radicado(texto: str) -> Radicado | None:
    m = _RE_RADICADO.search(texto)
    if not m:
        return None
    dane, esp, sala, desp, anio, cons, rec = m.groups()
    if not 1900 <= int(anio) <= _dt.date.today().year + 1:
        return None
    corp, etiqueta = _POR_PREFIJO.get(esp + sala, ("desconocida", ""))
    return Radicado(
        radicado=dane + esp + sala + desp + anio + cons + rec,
        formateado=f"{dane}-{esp}-{sala}-{desp}-{anio}-{cons}-{rec}",
        departamento=_DEPARTAMENTOS.get(dane[:2], ""),
        anio=anio,
        corporacion=corp,
        etiqueta=etiqueta,
    )
