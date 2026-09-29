"""Vigencia normativa como dato, no como texto que el modelo tenga que notar.

El 12-sep la app presentó como vigente la tarifa de un decreto inexequible
teniendo `<Decreto INEXEQUIBLE>` DENTRO del fragmento que recibió. La nota
estaba; lo que faltaba era que alguien la leyera por programa.

Las notas vienen de las fuentes oficiales (DIAN, sobre todo) con un formato
regular: `<Resolución derogada por el artículo 5 de la Resolución 12 de 2019>`,
`<Artículo INEXEQUIBLE>`, `NOTA DE VIGENCIA: Oficio revocado por…`. Se leen con
una regla, sin modelo.

Dos alcances, y no mezclarlos es la mitad del trabajo:

- **documento** — la nota dice "Decreto/Ley/Resolución/Oficio … derogado".
  Afecta a TODO el documento, pero suele aparecer solo en sus primeros
  fragmentos: el frag37 de un decreto derogado no lo dice. Por eso el estado del
  documento se precalcula recorriendo el corpus entero (`construir_tabla`) y se
  consulta por `documento_id`.
- **parcial** — "Artículo/Parágrafo/Inciso/Numeral/Aparte … derogado". Afecta al
  texto que la rodea, no a la norma. Se lee del propio fragmento.

Lo que NO cubre, dicho para que nadie lo dé por resuelto: normas cuyo texto no
trae nota (p. ej. la Ley 33 de 1986 en el corpus de legalize_co, derogada por el
Código de Tránsito de 2002). Para esas hace falta el catálogo de vigencias de
SUIN-Juriscol (datos.gov.co, fiev-nid6), que todavía no se ingiere.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

RUTA_TABLA = Path(
    os.environ.get("ALIADO_VIGENCIA", Path(__file__).resolve().parent / "vigencia_documentos.json")
)

# Estados, de peor a mejor. El orden importa: si un documento acumula notas
# distintas, manda la más grave.
INEXEQUIBLE = "inexequible"
DEROGADA = "derogada"
REVOCADA = "revocada"  # conceptos y oficios de la DIAN
SUSPENDIDA = "suspendida"
NULA = "nula"
# La nota nombra OTRA norma: "<Decreto 2788 de 2004 derogado…>" dentro del
# Decreto 65 de 2005, que modificaba al 2788. El que la contiene no está
# derogado, pero modifica algo que ya no rige: su vigencia queda en duda.
INCIERTA = "incierta"
VIGENTE = "sin_nota"  # nombre histórico: significa "sin nota", NO "vigente"
_GRAVEDAD = [INEXEQUIBLE, DEROGADA, NULA, REVOCADA, SUSPENDIDA, INCIERTA]

NO_VIGENTES = frozenset(_GRAVEDAD) - {INCIERTA}

_SUJETO_DOCUMENTO = r"(?:Decreto|Ley|Resoluci[oó]n|Oficio|Concepto|Circular|Acuerdo|Orden|Norma)"
_SUJETO_PARCIAL = (
    r"(?:Art[ií]culo|Par[aá]grafo|Inciso|Numeral|Literal|Aparte(?: tachado)?|Cap[ií]tulo|T[ií]tulo|Ordinal)"
)
_VERBO = (
    r"(?P<verbo>(?i:(?:declarad[oa]s? )?inexequibles?|derogad[oa]s?|revocad[oa]s?|"
    r"suspendid[oa]s?|declarad[oa]s? nul[oa]s?|nul[oa]s?))"
)

# Una nota: entre < > o tras "NOTA DE VIGENCIA:". Hasta 200 caracteres, porque
# el portal de la DIAN parte las referencias en varias líneas.
_NOTA = re.compile(
    r"(?:<\s*(?:NOTA DE VIGENCIA:\s*)?(?P<a>[^<>]{0,200}?)>)|(?:NOTA DE VIGENCIA:\s*(?P<b>[^\n<>]{0,200}))",
)
_ES_DOCUMENTO = re.compile(rf"^\s*{_SUJETO_DOCUMENTO}\b(?:\s+[\d.]+\s+de\s+\d{{4}})?\s+{_VERBO}")
_ES_PARCIAL = re.compile(rf"^\s*{_SUJETO_PARCIAL}\b[^<>]{{0,40}}?{_VERBO}")
# "<Derogado por el artículo 5 de la Ley…>" sin sujeto: en la práctica anota el
# artículo en el que está, así que es parcial.
_SIN_SUJETO = re.compile(rf"^\s*{_VERBO}\b")
_POR = re.compile(r"\bpor\s+(?:el|la|los|las)?\s*(?P<por>[^<>]{3,160})", re.IGNORECASE)


@dataclass(frozen=True)
class Nota:
    estado: str
    alcance: str  # "documento" | "parcial"
    texto: str
    por: str | None = None


def _estado(verbo: str) -> str:
    v = verbo.lower()
    if "inexequible" in v:
        return INEXEQUIBLE
    if "derogad" in v:
        return DEROGADA
    if "revocad" in v:
        return REVOCADA
    if "suspendid" in v:
        return SUSPENDIDA
    return NULA


def _limpio(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def leer_notas(texto: str) -> list[Nota]:
    """Todas las notas de vigencia de un fragmento, en orden de aparición."""
    notas = []
    for m in _NOTA.finditer(texto or ""):
        cuerpo = _limpio(m.group("a") if m.group("a") is not None else m.group("b"))
        if not cuerpo:
            continue
        # "Aparte tachado INEXEQUIBLE" empieza por un sujeto parcial pero dice
        # "tachado": se prueba parcial antes que documento.
        if mp := _ES_PARCIAL.match(cuerpo):
            alcance, verbo = "parcial", mp.group("verbo")
        elif md := _ES_DOCUMENTO.match(cuerpo):
            alcance, verbo = "documento", md.group("verbo")
        elif ms := _SIN_SUJETO.match(cuerpo):
            alcance, verbo = "parcial", ms.group("verbo")
        else:
            continue
        por = _POR.search(cuerpo)
        notas.append(Nota(_estado(verbo), alcance, cuerpo, _limpio(por.group("por")) if por else None))
    return notas


def _mas_grave(estados: list[str]) -> str:
    for e in _GRAVEDAD:
        if e in estados:
            return e
    return VIGENTE


def estado_de_notas(notas: list[Nota], alcance: str) -> Nota | None:
    candidatas = [n for n in notas if n.alcance == alcance]
    if not candidatas:
        return None
    peor = _mas_grave([n.estado for n in candidatas])
    return next(n for n in candidatas if n.estado == peor)


def documento_de(fragmento_id: str) -> str:
    return fragmento_id.split("::", 1)[0]


_NUMERADA = re.compile(r"^\S+\s+(?P<num>\d[\d.]*)\s+de\s+(?P<anio>\d{4})")


def atribuir(nota: Nota, documento_id: str) -> Nota:
    """Una nota de documento que nombra otra norma (número y año que no son los
    del documento que la contiene) no declara el estado de ESTE documento."""
    if nota.alcance != "documento" or not (m := _NUMERADA.match(nota.texto)):
        return nota
    numero = m.group("num").replace(".", "").lstrip("0")
    propio = re.sub(r"(?<=[_-])0+(?=\d)", "", documento_id)
    if m.group("anio") in documento_id and re.search(rf"(?<![\d]){numero}(?![\d])", propio):
        return nota
    return Nota(INCIERTA, "documento", nota.texto, nota.por)


# --- tabla por documento --------------------------------------------------


# --- catálogo oficial de SUIN-Juriscol (datos.gov.co, fiev-nid6) -----------

# Vigencia de SUIN -> (estado, alcance). SOLO los estados negativos, que son
# afirmaciones explícitas. Medido el 29-sep-2026: "Vigente" es el valor por
# omisión del catálogo, no una comprobación. Lo lleva la Ley 1943 de 2018,
# inexequible entera (C-481-19), la Ley 33 de 1986 y 29.250 de los decretos
# anteriores a 1960. "Compilado" lo lleva el Código Sustantivo del Trabajo.
# Mostrar cualquiera de los dos habría sido afirmar algo falso con sello
# oficial; no decir nada es mejor.
_SUIN = {
    "derogado": (DEROGADA, "documento"),
    "no vigente": (DEROGADA, "documento"),
    "sustituido": (DEROGADA, "documento"),
    "declarado inexequible": (INEXEQUIBLE, "documento"),
    "declarado nulo": (NULA, "documento"),
    "no ajustado a derecho": (NULA, "documento"),
    "suspendido provisionalmente": (SUSPENDIDA, "documento"),
    "derogado parcialmente": (DEROGADA, "parcial"),
    "inexequible parcialmente": (INEXEQUIBLE, "parcial"),
}
_TIPOS = {
    "ley": "LEY",
    "decreto": "DECRETO",
    "resolucion": "RESOLUCION",
    "acto-legislativo": "ACTO LEGISLATIVO",
    "acto_legislativo": "ACTO LEGISLATIVO",
    "acuerdo": "ACUERDO",
    "circular": "CIRCULAR",
}
# legalize_co_github:DECRETO-2503-1952 | dian:tributario:decreto_0150_1997
_ID_NORMA = re.compile(
    r"(?:^|:)(?P<tipo>ley|decreto|resolucion|acto[-_]legislativo|acuerdo|circular)"
    r"[-_](?P<num>\d+)[-_](?P<anio>\d{4})$",
    re.IGNORECASE,
)


def clave_norma(documento_id: str) -> tuple[str, str, str] | None:
    """(tipo, número sin ceros, año) si el id nombra una norma numerada."""
    m = _ID_NORMA.search(documento_id)
    if not m:
        return None
    return _TIPOS[m.group("tipo").lower()], m.group("num").lstrip("0") or "0", m.group("anio")


def indexar_suin(registros) -> dict[tuple[str, str, str], Nota]:
    """Registros del catálogo -> nota por (tipo, número, año). Si una clave
    aparece con vigencias distintas (normas homónimas de otra entidad), queda
    como incierta: no se adivina cuál es la del corpus."""
    vistas: dict[tuple, set] = {}
    for r in registros:
        vig = (r.get("vigencia") or "").strip().lower()
        num = (r.get("n_mero") or "").strip().lstrip("0") or "0"
        if vig not in _SUIN or not num.isdigit():
            continue
        clave = ((r.get("tipo") or "").strip().upper(), num, (r.get("a_o") or "").strip())
        vistas.setdefault(clave, set()).add(vig)
    salida = {}
    for clave, vigs in vistas.items():
        if len(vigs) == 1:
            vig = next(iter(vigs))
            estado, alcance = _SUIN[vig]
            texto = f"SUIN-Juriscol: {vig.capitalize()}"
        else:
            estado, alcance = INCIERTA, "documento"
            texto = (
                "SUIN-Juriscol: normas homónimas con vigencias distintas (" + ", ".join(sorted(vigs)) + ")"
            )
        salida[clave] = Nota(estado, alcance, texto, None)
    return salida


def construir_tabla(fragmentos, suin: dict | None = None) -> dict[str, dict]:
    """`fragmentos`: iterable de (id, texto). Devuelve documento_id -> nota.

    Combina dos fuentes: la nota oficial dentro del texto y, si se pasa, el
    catálogo de SUIN-Juriscol (`indexar_suin`). Si discrepan manda la más
    grave. Los documentos sin ninguna de las dos no se guardan: son
    `sin_nota` por omisión.
    """
    por_documento: dict[str, list[Nota]] = {}
    vistos: set[str] = set()
    for fragmento_id, texto in fragmentos:
        doc = documento_de(fragmento_id)
        vistos.add(doc)
        notas = [atribuir(n, doc) for n in leer_notas(texto) if n.alcance == "documento"]
        if notas:
            por_documento.setdefault(doc, []).extend(notas)
    if suin:
        for doc in vistos:
            clave = clave_norma(doc)
            if clave and clave in suin:
                por_documento.setdefault(doc, []).append(suin[clave])
    tabla = {}
    for doc, notas in por_documento.items():
        peor = _mas_grave([n.estado for n in notas])
        # Entre notas del mismo estado, la del texto (con su "por") va primero.
        tabla[doc] = asdict(next(n for n in notas if n.estado == peor))
    return tabla


_tabla: dict[str, dict] | None = None


def tabla() -> dict[str, dict]:
    """Carga perezosa. Sin tabla en disco devuelve {} y el sistema cae a leer
    solo el propio fragmento: peor, pero nunca peor que antes de este módulo."""
    global _tabla
    if _tabla is None:
        try:
            _tabla = json.loads(RUTA_TABLA.read_text(encoding="utf-8"))["documentos"]
        except (OSError, ValueError, KeyError):
            _tabla = {}
    return _tabla


def vigencia_de(resultado: dict) -> dict:
    """Estado de vigencia de un resultado de búsqueda, como dict serializable."""
    # La clave es el id del fragmento sin "::fragN" ("dian:tributario:decreto_0433_1999").
    # `identificador_documento` NO sirve: viene sin el prefijo de la fuente.
    doc_id = (
        documento_de(resultado["id"]) if resultado.get("id") else resultado.get("identificador_documento", "")
    )
    notas = [atribuir(n, doc_id) for n in leer_notas(resultado.get("texto", ""))]
    documentales = [n for n in notas if n.alcance == "documento"]
    if fila := tabla().get(doc_id):
        documentales.append(Nota(**fila))
    nota_doc = None
    if documentales:
        peor = _mas_grave([n.estado for n in documentales])
        nota_doc = next(n for n in documentales if n.estado == peor)

    def _dict(n: Nota) -> dict:
        return {"estado": n.estado, "alcance": n.alcance, "nota": n.texto, "por": n.por}

    # Orden: la norma entera no rige > este texto tiene partes que no rigen >
    # lo demás (incierta, parcialmente derogada según el catálogo).
    if nota_doc is not None and nota_doc.alcance == "documento" and nota_doc.estado in NO_VIGENTES:
        return _dict(nota_doc)
    if (nota_parcial := estado_de_notas(notas, "parcial")) is not None:
        return _dict(nota_parcial)
    if nota_doc is not None:
        return _dict(nota_doc)
    return {"estado": VIGENTE, "alcance": None, "nota": None, "por": None}


def anotar(resultados: list[dict]) -> list[dict]:
    """Añade la clave `vigencia` a cada resultado (in situ) y los devuelve."""
    for r in resultados:
        r["vigencia"] = vigencia_de(r)
    return resultados


def documento_no_vigente(resultado: dict) -> bool:
    v = resultado.get("vigencia") or vigencia_de(resultado)
    return v["alcance"] == "documento" and v["estado"] in NO_VIGENTES


def etiqueta(v: dict) -> str:
    """Una línea legible, para el prompt, la GUI y el MCP."""
    if v["estado"] == VIGENTE:
        return "Sin nota de vigencia en el texto (no prueba que esté vigente)."
    if v["estado"] == INCIERTA:
        return f"VIGENCIA INCIERTA: verifica antes de aplicarla — «{v['nota']}»"
    if v["alcance"] == "documento":
        quien = "TODA LA NORMA"
    elif (v.get("nota") or "").startswith("SUIN"):
        quien = "PARTE DE LA NORMA"
    else:
        quien = "PARTE DE ESTE TEXTO"
    return f"{quien}: {v['estado'].upper()} — «{v['nota']}»"


# --- guarda sobre la respuesta generada ------------------------------------

_ADVIRTIO = re.compile(
    r"derogad|inexequib|revocad|suspendid|no (?:est[aá]|se encuentra) vigente|ya no rige|"
    r"dej[oó] de regir|perdi[oó] (?:su )?vigencia|no rige|nulidad|declarad[oa] nul",
    re.IGNORECASE,
)


def garantizar_advertencia(respuesta: str, resultados: list[dict]) -> str:
    """Si la respuesta se apoya en fragmentos de normas no vigentes y no lo
    advierte, se le antepone la advertencia. Determinista: no depende de que el
    modelo lea la nota, que es justo lo que falló el 12-sep."""
    malas = []
    for r in resultados:
        v = r.get("vigencia") or vigencia_de(r)
        if v["alcance"] == "documento" and v["estado"] in NO_VIGENTES:
            nombre = r.get("titulo_documento") or r.get("identificador_documento") or "una norma"
            if nombre not in [m[0] for m in malas]:
                malas.append((nombre, v))
    if not malas or _ADVIRTIO.search(respuesta or ""):
        return respuesta
    lineas = [f"- {nombre}: {v['estado'].upper()} (nota oficial: «{v['nota']}»)" for nombre, v in malas[:3]]
    return (
        "⚠ ADVERTENCIA DE VIGENCIA: parte de lo que se usó para esta respuesta NO está "
        "vigente según su propia nota oficial. No la apliques sin verificar la norma que "
        "la reemplazó.\n" + "\n".join(lineas) + "\n\n" + (respuesta or "")
    )
