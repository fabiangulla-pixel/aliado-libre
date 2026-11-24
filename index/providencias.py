"""Providencias de la Corte Suprema: identificadores, ficha, enlaces y relaciones.

Todo LOCAL. El catálogo (`index/catalogo_suprema.json`) y las relaciones
(`index/relaciones_suprema.db`) se construyen una vez desde los datos crudos
(`data/raw/corte_suprema*.json`), sin red y sin reindexar Chroma: los
resultados de la búsqueda se enriquecen al vuelo por `documento_id`, igual que
la vigencia (`index/vigencia.py`).

    .venv/Scripts/python.exe -m index.providencias --construir
    .venv/Scripts/python.exe -m index.providencias "CSJ SL131-2026"

Identificadores: solo los prefijos con ejemplos reales en el corpus (conteo
del 23-nov-2026 sobre 1 de cada 5 textos: SL 57.778, SC 1.169, AL 587,
STL 140, STC 124, AC 74, STP 33, AP 5, SP 4). «SU-837-2002» es de la Corte
Constitucional y lo sigue resolviendo `index/citas.py`.

OJEADOR (ojeador.cortesuprema.gov.co), comprobado el 23-nov-2026:
- La ficha es `/caso/<numerador>`; con duplicados, `?doc=<Hash>` la precisa.
  Es una aplicación de una sola página: responde 200 a CUALQUIER numerador,
  así que el enlace por sí solo no prueba nada. Solo se presenta como ficha
  oficial si `scripts/ojeador_verificar.py` (opcional, con red, a petición)
  confirmó UNA coincidencia exacta en el servicio de la Corte.
- Sin verificación se ofrece "Buscar en Ojeador" (`/resultados?q=`), que es
  una búsqueda, no la ficha.
- El servicio no tiene API pública documentada (su /docs responde 401): se usa
  solo como verificación opcional, nunca como dependencia.
"""

from __future__ import annotations

import ast
import datetime as _dt
import json
import os
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = Path(os.environ.get("ALIADO_CATALOGO_SUPREMA", RAIZ / "index" / "catalogo_suprema.json"))
RELACIONES = Path(os.environ.get("ALIADO_RELACIONES_SUPREMA", RAIZ / "index" / "relaciones_suprema.db"))
VERIFICACION = RAIZ / "data" / "ojeador" / "verificacion.jsonl"
RAW = (RAIZ / "data" / "raw" / "corte_suprema.json", RAIZ / "data" / "raw" / "corte_suprema_ocr.json")

CORPORACION = "Corte Suprema de Justicia"
OJEADOR = "https://ojeador.cortesuprema.gov.co"
OJEADOR_ARCHIVO = "https://buscadorjurisprudenciabackend.cortesuprema.gov.co/document/descargar?path="
BUSCADOR_ANTIGUO = "https://consultaprovidencias.cortesuprema.gov.co/"

# prefijo -> (sala, tipo de providencia)
PREFIJOS: dict[str, tuple[str, str]] = {
    "SL": ("Laboral", "sentencia"),
    "SC": ("Civil", "sentencia"),
    "SP": ("Penal", "sentencia"),
    "AL": ("Laboral", "auto"),
    "AC": ("Civil", "auto"),
    "AP": ("Penal", "auto"),
    "STL": ("Laboral", "sentencia de tutela"),
    "STC": ("Civil", "sentencia de tutela"),
    "STP": ("Penal", "sentencia de tutela"),
    # vistos en la muestra oficial de Ojeador (23-nov-2026), no en el corpus
    "ATL": ("Laboral", "auto de tutela"),
    "ATC": ("Civil", "auto de tutela"),
    "AHL": ("Laboral", "auto de hábeas corpus"),
}
_ALT = "|".join(sorted(PREFIJOS, key=len, reverse=True))
# Mayúsculas obligatorias: «al 12-2020» en prosa no es un auto. El número es
# entero (sin tope que lo parta) y el año va de 1990 al próximo.
_RE_COMPLETA = re.compile(
    rf"(?<![A-Za-z0-9])({_ALT})\s?[-.]?\s?(\d{{1,5}})([A-Z]?)\s?(?:-|/|\s+de\s+)\s?(\d{{4}})(?![\d])"
)
# "SL131" sin año: referencia incompleta. No se resuelve en silencio.
_RE_INCOMPLETA = re.compile(rf"(?<![A-Za-z0-9])({_ALT})\s?[-.]?\s?(\d{{1,5}})([A-Z]?)(?![\w-])")


@dataclass(frozen=True)
class RefProvidencia:
    prefijo: str
    numero: int
    letra: str
    anio: str | None
    original: str
    inicio: int
    fin: int

    @property
    def completa(self) -> bool:
        return self.anio is not None

    @property
    def canonica(self) -> str:
        """SL131-2026. Los ceros a la izquierda no distinguen: SC016-2018 == SC16-2018."""
        base = f"{self.prefijo}{self.numero}{self.letra}"
        return f"{base}-{self.anio}" if self.anio else base

    @property
    def sala(self) -> str:
        return PREFIJOS[self.prefijo][0]

    @property
    def tipo(self) -> str:
        return PREFIJOS[self.prefijo][1]


def _anio_valido(a: str) -> bool:
    return 1990 <= int(a) <= _dt.date.today().year + 1


def referencias(texto: str) -> list[RefProvidencia]:
    """Todas las providencias de la Suprema citadas con identificador completo."""
    salida = []
    for m in _RE_COMPLETA.finditer(texto or ""):
        if not _anio_valido(m.group(4)):
            continue
        salida.append(
            RefProvidencia(
                m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(0), m.start(), m.end()
            )
        )
    return salida


def parsear(texto: str) -> RefProvidencia | None:
    """La primera referencia: completa si la hay; si no, incompleta (sin año)."""
    refs = referencias(texto)
    if refs:
        return refs[0]
    for m in _RE_INCOMPLETA.finditer(texto or ""):
        return RefProvidencia(m.group(1), int(m.group(2)), m.group(3), None, m.group(0), m.start(), m.end())
    return None


def canonica(identificador: str) -> str | None:
    r = referencias(identificador)
    return r[0].canonica if r and r[0].original.strip() == identificador.strip() else None


# --- citas antiguas: sala + fecha + radicado -------------------------------
#
# Antes de los identificadores SL/SC (la Sala Laboral los usa desde 2016) la
# Suprema se citaba por fecha y radicado: «CSJ SL, 5 ago. 2014, rad. 45678»,
# «Sala de Casación Laboral, sentencia del 5 de agosto de 2014, radicación
# 45678». Se reconocen solo con un ancla de la Suprema antes de la fecha o con
# un radicado pegado a ella: una fecha suelta en prosa no es una cita.

_MESES_ABREV = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "sept": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}  # fmt: skip
_ALT_MES = "|".join(sorted(list(_MESES_ABREV) + ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                    "julio", "agosto", "septiembre", "setiembre", "octubre", "noviembre", "diciembre"],
                   key=len, reverse=True))  # fmt: skip
_RE_FECHA_CITA = re.compile(
    rf"(?<![\d])(\d{{1,2}})(?:\s*(?:de|-|/))?\s*({_ALT_MES})\b\.?(?:\s*(?:de|del|-|/|,))?\s*(\d{{4}})(?!\d)",
    re.I,
)
# Sala por la sigla tras «CSJ» o por el nombre: SL / SCL = Laboral, SC / SCC = Civil, SP / SCP = Penal.
_RE_SALA_SIGLA = re.compile(r"\bCSJ\b[\s,.]*(SCL|SCC|SCP|STL|STC|STP|SL|SC|SP|AL|AC|AP)\b")
_SIGLA_SALA = {"L": "Laboral", "C": "Civil", "P": "Penal"}
_RE_SALA_NOMBRE = re.compile(r"Sala\s+(?:de\s+)?(?:Casaci[oó]n\s+)?(Laboral|Civil|Penal)", re.I)
_RE_ANCLA = re.compile(r"\bCSJ\b|Corte\s+Suprema|Sala\s+de\s+Casaci[oó]n", re.I)
_RE_RAD_CITA = re.compile(
    r"\brad(?:icaci[oó]n|icado|\.)?\s*(?:n(?:[uú]mero|o)?\s*\.?\s*[°º]?\s*\.?)?\s*:?\s*"
    r"(\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}|\d{3,7})(?![\d-])",
    re.I,
)
_RE_OTRA_CORPORACION = re.compile(
    r"Consejo\s+de\s+Estado|Corte\s+Constitucional|Tribunal|Juzgado|Secci[oó]n\s+(?:Primera|Segunda|Tercera|Cuarta|Quinta)"
    r"|\bC\.\s?E\.|\bCE\b|\bCC\b",
    re.I,
)
# «Sala de Casación Laboral. Sentencia del 5 de agosto…» sigue siendo la misma cita
_RE_FIN_ORACION = re.compile(r"[.;]\s+(?=[A-ZÁÉÍÓÚÑ¿])(?!Sentencia|Providencia|Auto\b|M\.\s?P|Rad)|\n\s*\n")
_VENTANA_ANCLA = 160
_VENTANA_RAD = 70


@dataclass(frozen=True)
class RefAntigua:
    sala: str | None
    fecha: str  # ISO, completa: sin día no hay cita antigua que resolver
    radicado: str | None
    original: str
    inicio: int
    fin: int
    # «CSJ SC1171, rad. …, 8 abr. 2022»: número sin año + año de la fecha
    identificador: str | None = None

    @property
    def etiqueta(self) -> str:
        if self.identificador:
            return self.identificador
        partes = ["CSJ" + (f" {self.sala}" if self.sala else ""), self.fecha]
        if self.radicado:
            partes.append(f"rad. {self.radicado}")
        return ", ".join(partes)


def _sala_en(texto: str) -> str | None:
    ultima = None
    for m in _RE_SALA_SIGLA.finditer(texto):
        ultima = (m.start(), _SIGLA_SALA[m.group(1)[-1]])
    for m in _RE_SALA_NOMBRE.finditer(texto):
        if ultima is None or m.start() > ultima[0]:
            ultima = (m.start(), m.group(1).capitalize())
    return ultima[1] if ultima else None


def referencias_antiguas(texto: str) -> list[RefAntigua]:
    """Citas de la Suprema por fecha (y radicado), sin identificador SL/SC."""
    texto = texto or ""
    nuevas = referencias(texto)
    salida = []
    for m in _RE_FECHA_CITA.finditer(texto):
        mes = m.group(2).lower()
        mes_n = _MESES.get(mes) or _MESES_ABREV.get(mes)
        try:
            fecha = _dt.date(int(m.group(3)), mes_n, int(m.group(1)))
        except (ValueError, TypeError):
            continue
        if not 1886 <= fecha.year <= _dt.date.today().year:
            continue
        # si hay un identificador nuevo pegado, la cita ya está resuelta por él
        # («SL131-2026 del 11 de febrero de 2026», «11 feb. 2026 (SL131-2026)»)
        if any(0 <= m.start() - r.fin <= 8 or 0 <= r.inicio - m.end() <= 3 for r in nuevas):
            continue
        antes = texto[max(0, m.start() - _VENTANA_ANCLA) : m.start()]
        # el ancla tiene que estar en la misma oración: «rad.» o «ago.» no la cortan
        cortes = list(_RE_FIN_ORACION.finditer(antes))
        cerca = antes[cortes[-1].end() :] if cortes else antes
        fin, radicado = m.end(), None
        tras = _RE_RAD_CITA.search(texto[m.end() : m.end() + _VENTANA_RAD])
        # «…de 2014, rad. 45678»; no «…2017». SCLAPT-10 V.00 10 Radicación n.° 79767»,
        # que es el encabezado de página del propio documento
        if (
            tras
            and tras.start() <= 25
            and not re.search(r"[.;»)]\s", texto[m.end() : m.end() + tras.start()])
        ):
            fin, radicado = m.end() + tras.end(), tras.group(1)
        else:  # «rad. 45678 del 5 de agosto de 2014»
            previos = list(_RE_RAD_CITA.finditer(cerca[-_VENTANA_RAD:]))
            radicado = previos[-1].group(1) if previos else None
        # un identificador completo en la misma frase se lleva el ancla: «CSJ
        # SL1671-2023, esta Sala CASÓ la proferida el 30 de septiembre…» no cita
        # una providencia del 30 de septiembre, habla del fallo del tribunal
        ancla = list(_RE_ANCLA.finditer(cerca))
        desde = m.start() - len(cerca) + (ancla[-1].start() if ancla else 0)
        if any(r.inicio >= desde and r.fin <= m.start() for r in nuevas):
            continue
        otra = list(_RE_OTRA_CORPORACION.finditer(cerca))
        if otra and (not ancla or otra[-1].start() > ancla[-1].start()):
            continue  # la corporación más cercana a la fecha no es la Suprema
        if not ancla and radicado is None:
            continue
        inicio = m.start()
        if ancla:
            inicio = m.start() - len(cerca) + ancla[-1].start()
        # número sin año entre el ancla y la fecha: el año lo pone la fecha
        tramo = cerca[ancla[-1].start() :] if ancla else cerca
        sin_anio = list(_RE_INCOMPLETA.finditer(tramo))
        identificador = None
        if sin_anio:
            s = sin_anio[-1]
            identificador = f"{s.group(1)}{int(s.group(2))}{s.group(3)}-{fecha.year}"
        salida.append(
            RefAntigua(
                sala=PREFIJOS[sin_anio[-1].group(1)][0] if sin_anio else _sala_en(cerca),
                fecha=fecha.isoformat(),
                radicado=radicado,
                original=re.sub(r"\s+", " ", texto[inicio:fin]).strip(),
                inicio=inicio,
                fin=fin,
                identificador=identificador,
            )
        )
    return salida


def parsear_antigua(texto: str) -> RefAntigua | None:
    refs = referencias_antiguas(texto)
    return refs[0] if refs else None


def _indices(documentos: dict) -> tuple[dict, dict]:
    por_fecha: dict[str, list[str]] = {}
    por_rad: dict[str, list[str]] = {}
    for did, f in documentos.items():
        if f.get("fecha_precision") == "dia" and f.get("fecha"):
            por_fecha.setdefault(f["fecha"], []).append(did)
        if f.get("radicado"):
            por_rad.setdefault(f["radicado"], []).append(did)
    return por_fecha, por_rad


def candidatos_antigua(
    ref: RefAntigua,
    documentos: dict,
    indices: tuple[dict, dict] | None = None,
    por_canonica: dict | None = None,
) -> list[str]:
    """Providencias del catálogo compatibles con la cita antigua.

    Con número de providencia (SC1171 + año de la fecha): esa, si está. Si no,
    con radicado: las de ese radicado y esa fecha; si ninguna tiene fecha
    completa, las de ese radicado y ese AÑO (la fecha del índice se quedó en el
    año: compatibles, no confirmadas). Sin radicado: las de esa fecha (y sala),
    salvo que la cita traiga un número que no está: entonces ninguna.
    Nunca se elige entre varias: se devuelven todas."""
    if ref.identificador:
        pc = por_canonica if por_canonica is not None else catalogo().get("por_canonica", {})
        if pc.get(ref.identificador):
            return list(pc[ref.identificador])
        if not ref.radicado:
            return []  # «SC22056 de 19 dic. 2017» no es «la otra de esa fecha»
    por_fecha, por_rad = indices or _indices(documentos)
    if ref.radicado:
        mismas = por_rad.get(ref.radicado, [])
        c = [d for d in mismas if documentos[d].get("fecha") == ref.fecha]
        if not c:
            c = [
                d
                for d in mismas
                if documentos[d].get("fecha_precision") != "dia"
                and str(documentos[d].get("fecha") or "")[:4] == ref.fecha[:4]
            ]
    else:
        c = list(por_fecha.get(ref.fecha, []))
    if ref.sala:
        c = [d for d in c if documentos[d].get("sala") in (ref.sala, None)]
    return c


# --- metadatos desde el texto ---------------------------------------------

_MESES = {
    m: i + 1
    for i, m in enumerate(
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
    )
}
_MESES["setiembre"] = 9
_RE_FECHA = re.compile(
    r"\((\d{1,2})\)\s+de\s+(" + "|".join(_MESES) + r")\s+de\s+[^()]{3,60}?\((\d{4})\)", re.I
)
_RE_RADICACION = re.compile(
    r"Radica(?:ci[oó6]n|do)\s*(?:n(?:\.|ú|u)?(?:mero)?\s*\.?\s*[°ºo]?\s*\.?|No\.?)?\s*:?\s*"
    r"([0-9][0-9 .-]{3,40}[0-9])",
    re.I,
)


def fecha_del_encabezado(texto: str, anio: str | None) -> str | None:
    """Fecha de la providencia si el encabezado la trae completa y concuerda con el año.

    "Bogotá D. C., once (11) de febrero de dos mil veintiséis (2026)". Sin
    eso, None: nunca se inventan día ni mes."""
    m = _RE_FECHA.search((texto or "")[:3000])
    if not m:
        return None
    dia, mes, a = int(m.group(1)), _MESES[m.group(2).lower()], m.group(3)
    if anio and a != str(anio)[:4]:
        return None
    try:
        return _dt.date(int(a), mes, dia).isoformat()
    except ValueError:
        return None


def radicado_del_encabezado(texto: str) -> tuple[str, str] | None:
    """(radicado, tipo): "cui" si son los 23 dígitos del radicado único; "interno" si es corto."""
    m = _RE_RADICACION.search((texto or "")[:3000])
    if not m:
        return None
    digitos = re.sub(r"\D", "", m.group(1))
    if len(digitos) == 23:
        d = digitos
        return f"{d[:5]}-{d[5:7]}-{d[7:9]}-{d[9:12]}-{d[12:16]}-{d[16:21]}-{d[21:]}", "cui"
    if 3 <= len(digitos) <= 7:
        return digitos, "interno"
    return None


def _metadata(x: dict) -> dict:
    m = x.get("metadata") or {}
    if isinstance(m, str):  # los JSON crudos guardaron el repr del dict
        try:
            m = ast.literal_eval(m)
        except (ValueError, SyntaxError):
            m = {}
    return m if isinstance(m, dict) else {}


def ficha_desde_crudo(x: dict, origen_ocr: bool) -> dict:
    m = _metadata(x)
    ref = referencias(x.get("identificador") or "")
    prefijo = ref[0].prefijo if ref else None
    sala = m.get("sala") or (PREFIJOS[prefijo][0] if prefijo else None)
    anio = str(x.get("fecha") or "")[:4] or None
    fecha = fecha_del_encabezado(x.get("texto", ""), anio)
    rad = radicado_del_encabezado(x.get("texto", ""))
    paginas, paginas_ocr = m.get("paginas"), m.get("paginas_ocr")
    if origen_ocr and paginas_ocr:
        origen = "ocr" if not paginas or paginas_ocr >= paginas else "mixto"
    else:
        origen = "digital"
    return {
        "numerador": x.get("identificador"),
        "canonica": ref[0].canonica if ref else None,
        "corporacion": CORPORACION,
        "sala": sala,
        "tipo_providencia": PREFIJOS[prefijo][1] if prefijo else x.get("tipo"),
        "radicado": rad[0] if rad else None,
        "radicado_tipo": rad[1] if rad else None,
        "fecha": fecha or anio,
        "fecha_precision": "dia" if fecha else ("anio" if anio else None),
        "fecha_origen": "encabezado del texto" if fecha else ("año del buscador" if anio else None),
        "ponente": (m.get("magistrado") or "").strip() or None,
        "ruta_archivo": m.get("ruta"),
        "origen_texto": origen,
        "confianza_ocr": round(float(m["confianza_ocr"]), 3) if m.get("confianza_ocr") else None,
        "paginas": paginas,
        "paginas_ocr": paginas_ocr,
        "url_buscador": x.get("url_original") or BUSCADOR_ANTIGUO,
    }


# --- verificación opcional contra Ojeador ---------------------------------


def leer_verificacion(ruta: Path = VERIFICACION) -> dict[str, dict]:
    """canónica -> último registro de `scripts/ojeador_verificar.py`."""
    out: dict[str, dict] = {}
    if not ruta.exists():
        return out
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if r.get("canonica"):
            out[r["canonica"]] = r
    return out


def enlaces(f: dict, verif: dict | None) -> dict:
    """Enlaces separados por lo que son. `ficha` y `archivo` SOLO si están verificados."""
    numerador = f.get("numerador") or ""
    salida = {
        "ficha": None,
        "archivo": None,
        "buscar_en_ojeador": f"{OJEADOR}/resultados?q={quote(numerador)}" if numerador else None,
        "buscador_general": f.get("url_buscador") or BUSCADOR_ANTIGUO,
        "estado": "no_verificado",
        "verificado_el": None,
    }
    if verif:
        salida["verificado_el"] = verif.get("consultado")
        salida["estado"] = verif.get("estado", "no_verificado")
        if verif.get("estado") == "verificada" and verif.get("hash"):
            salida["ficha"] = (
                f"{OJEADOR}/caso/{quote(verif.get('numerador') or numerador)}?doc={quote(verif['hash'])}"
            )
            if verif.get("ubicacion"):
                salida["archivo"] = OJEADOR_ARCHIVO + quote(verif["ubicacion"])
    return salida


# --- construcción del catálogo y las relaciones ----------------------------


def _contexto(texto: str, inicio: int, fin: int, ancho: int = 160) -> str:
    a, b = max(0, inicio - ancho), min(len(texto), fin + ancho)
    return re.sub(r"\s+", " ", ("…" if a else "") + texto[a:b] + ("…" if b < len(texto) else "")).strip()


def construir(rutas=RAW, catalogo: Path = CATALOGO, relaciones: Path = RELACIONES) -> dict:
    documentos: dict[str, dict] = {}
    textos: dict[str, str] = {}
    for ruta in rutas:
        ruta = Path(ruta)
        if not ruta.exists():
            continue
        es_ocr = "ocr" in ruta.name
        for x in json.loads(ruta.read_text(encoding="utf-8")):
            if x.get("fuente") != "corte_suprema" or x["id"] in documentos:
                continue
            # NFKC: el OCR deja guiones y paréntesis de ancho completo
            # ("SC674－2020", "（2020）") que ninguna regla reconocería.
            x = {**x, "texto": unicodedata.normalize("NFKC", x.get("texto") or "")}
            documentos[x["id"]] = ficha_desde_crudo(x, es_ocr)
            textos[x["id"]] = x["texto"]
    por_canonica: dict[str, list[str]] = {}
    for did, f in documentos.items():
        if f["canonica"]:
            por_canonica.setdefault(f["canonica"], []).append(did)

    indices = _indices(documentos)

    tmp = relaciones.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute(
        "create table citas (origen text, canonica text, original text, estado text, destino text,"
        " veces integer, contexto text)"
    )
    filas = []
    for did, texto in textos.items():
        propia = documentos[did]["canonica"]
        vistas: dict[str, list] = {}
        for r in referencias(texto):
            if r.canonica == propia:
                continue  # el encabezado se nombra a sí mismo
            if r.canonica in vistas:
                vistas[r.canonica][5] += 1
                continue
            destinos = por_canonica.get(r.canonica, [])
            estado = "confirmada" if len(destinos) == 1 else ("ambigua" if destinos else "no_resuelta")
            vistas[r.canonica] = [
                did,
                r.canonica,
                r.original,
                estado,
                destinos[0] if len(destinos) == 1 else None,
                1,
                _contexto(texto, r.inicio, r.fin),
            ]
        # Citas antiguas: «confirmada» con número + año o con radicado + fecha
        # exactos; radicado + año (el índice no sabe el día) es «probable»;
        # varias, «ambigua». Con SOLO la fecha no se crea relación: medido el
        # 23-nov, casi siempre es la fecha del fallo de instancia («NO CASA la
        # sentencia proferida el 13 de diciembre de 2018»), no una cita.
        for r in referencias_antiguas(texto):
            if not (r.radicado or r.identificador):
                continue
            clave = r.etiqueta
            if clave == propia:
                continue
            if clave in vistas:
                vistas[clave][5] += 1
                continue
            destinos = [d for d in candidatos_antigua(r, documentos, indices, por_canonica) if d != did]
            if len(destinos) == 1:
                f = documentos[destinos[0]]
                exacta = f.get("canonica") == r.identificador or f.get("fecha") == r.fecha
                estado = "confirmada" if exacta else "probable"
            else:
                estado = "ambigua" if destinos else "no_resuelta"
            vistas[clave] = [
                did,
                clave,
                r.original,
                estado,
                destinos[0] if len(destinos) == 1 else None,
                1,
                _contexto(texto, r.inicio, r.fin),
            ]
        filas.extend(vistas.values())
    con.executemany("insert into citas values (?,?,?,?,?,?,?)", filas)
    con.execute("create index i_origen on citas(origen)")
    con.execute("create index i_destino on citas(destino)")
    con.execute("create index i_canonica on citas(canonica)")
    con.commit()
    con.close()
    tmp.replace(relaciones)

    datos = {
        "generado": _dt.datetime.now().isoformat(timespec="seconds"),
        "fuentes": [str(Path(r).name) for r in rutas if Path(r).exists()],
        "documentos": documentos,
        "por_canonica": por_canonica,
        "relaciones": {
            "total": len(filas),
            "confirmadas": sum(f[3] == "confirmada" for f in filas),
            "probables": sum(f[3] == "probable" for f in filas),
            "ambiguas": sum(f[3] == "ambigua" for f in filas),
            "no_resueltas": sum(f[3] == "no_resuelta" for f in filas),
        },
    }
    t = catalogo.with_suffix(".tmp")
    t.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    t.replace(catalogo)
    global _cat
    _cat = None
    return datos


# --- consulta -------------------------------------------------------------

_cat: dict | None = None
_verif: dict | None = None


def catalogo() -> dict:
    global _cat, _verif
    if _cat is None:
        try:
            _cat = json.loads(CATALOGO.read_text(encoding="utf-8")) if CATALOGO.exists() else {}
        except (OSError, ValueError):
            _cat = {}
        _verif = leer_verificacion()
    return _cat


def disponible() -> bool:
    return bool(catalogo().get("documentos"))


def documentos_de(canon: str) -> list[str]:
    return list(catalogo().get("por_canonica", {}).get(canon, []))


def ficha(documento_id: str) -> dict | None:
    """Ficha de una providencia de la Suprema del índice, o None si no la hay."""
    f = catalogo().get("documentos", {}).get(documento_id)
    if f is None:
        return None
    v = (_verif or {}).get(f.get("canonica") or "")
    salida = {**f, "documento_id": documento_id, "enlaces": enlaces(f, v)}
    if v and v.get("estado") == "verificada":
        # lo que la Corte publica manda sobre lo que se dedujo del texto
        if v.get("fecha"):
            salida.update(fecha=v["fecha"], fecha_precision="dia", fecha_origen="Ojeador (Corte Suprema)")
        if v.get("cui") and not salida.get("radicado"):
            d = v["cui"]
            salida["radicado"] = f"{d[:5]}-{d[5:7]}-{d[7:9]}-{d[9:12]}-{d[12:16]}-{d[16:21]}-{d[21:]}"
            salida["radicado_tipo"] = "cui"
        for k in ("clase_actuacion", "tema"):
            if v.get(k):
                salida[k] = v[k]
    return salida


def _documento_id(r: dict) -> str:
    return r.get("documento_id") or str(r.get("id", "")).split("::")[0]


def anotar(resultados: list[dict]) -> list[dict]:
    """Agrega `ficha` a los resultados de la Suprema. Sin catálogo, no toca nada."""
    if not disponible():
        return resultados
    salida = []
    for r in resultados:
        if r.get("fuente") == "corte_suprema" or _documento_id(r).startswith("corte_suprema:"):
            f = ficha(_documento_id(r))
            if f:
                r = {**r, "ficha": f}
        salida.append(r)
    return salida


def relaciones(documento_id: str, limite: int = 50) -> dict:
    """«Cita a» y «es citada por», con su contexto. Coincidencia de identificador,
    NO análisis jurídico: no dice si reitera, cambia o sigue el precedente."""
    vacio = {"cita_a": [], "citada_por": [], "total_cita_a": 0, "total_citada_por": 0}
    f = catalogo().get("documentos", {}).get(documento_id)
    if f is None or not RELACIONES.exists():
        return vacio
    con = sqlite3.connect(f"file:{RELACIONES}?mode=ro", uri=True)
    try:
        sal = con.execute(
            "select canonica, original, estado, destino, veces, contexto from citas where origen=?"
            " order by veces desc, canonica limit ?",
            (documento_id, limite),
        ).fetchall()
        n_sal = con.execute("select count(*) from citas where origen=?", (documento_id,)).fetchone()[0]
        canon = f.get("canonica")
        ent = con.execute(
            "select origen, original, estado, veces, contexto from citas where destino=?"
            " or (canonica=? and estado='ambigua') order by origen desc limit ?",
            (documento_id, canon, limite),
        ).fetchall()
        n_ent = con.execute(
            "select count(*) from citas where destino=? or (canonica=? and estado='ambigua')",
            (documento_id, canon),
        ).fetchone()[0]
    finally:
        con.close()
    docs = catalogo().get("documentos", {})
    return {
        "cita_a": [
            {
                "identificador": c,
                "como_aparece": o,
                "estado": e,
                "documento_id": d,
                "veces": v,
                "contexto": ctx,
                "en_indice": d is not None,
            }
            for c, o, e, d, v, ctx in sal
        ],
        "citada_por": [
            {
                "identificador": (docs.get(o) or {}).get("numerador") or o,
                "documento_id": o,
                "como_aparece": orig,
                "estado": e,
                "veces": v,
                "contexto": ctx,
                "fecha": (docs.get(o) or {}).get("fecha"),
            }
            for o, orig, e, v, ctx in ent
        ],
        "total_cita_a": n_sal,
        "total_citada_por": n_ent,
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:] == ["--construir"]:
        d = construir()
        n, ids = len(d["documentos"]), len(d["por_canonica"])
        print(f"{n} providencias; {ids} identificadores; relaciones {d['relaciones']}")
    else:
        ref = parsear(" ".join(sys.argv[1:]))
        print(ref)
        if ref and ref.completa:
            for did in documentos_de(ref.canonica):
                print(json.dumps(ficha(did), ensure_ascii=False, indent=1))
                rel = relaciones(did, 5)
                print("cita a:", rel["total_cita_a"], "| citada por:", rel["total_citada_por"])


# --- filtros --------------------------------------------------------------

SALAS = ("Laboral", "Civil", "Penal")
TIPOS = ("sentencia", "auto", "sentencia de tutela", "auto de tutela", "auto de hábeas corpus")


def filtros_desde_parametros(params: dict) -> dict:
    """Filtros válidos de una petición (parse_qs). Valores desconocidos se ignoran."""

    def uno(clave: str) -> str:
        return ((params.get(clave) or [""])[0] or "").strip()

    f: dict = {}
    sala = uno("sala").capitalize()
    if sala in SALAS:
        f["sala"] = sala
    tipo = uno("tipo_providencia").lower()
    if tipo in TIPOS:
        f["tipo_providencia"] = tipo
    for clave in ("anio_desde", "anio_hasta"):
        v = uno(clave)
        if v.isdigit() and 1900 <= int(v) <= _dt.date.today().year + 1:
            f[clave] = int(v)
    return f


def cumple(resultado: dict, filtros: dict) -> bool:
    """¿El resultado (ya anotado) pasa los filtros? Sin ficha no pasa: no se sabe."""
    f = resultado.get("ficha")
    if not f:
        return False
    if "sala" in filtros and f.get("sala") != filtros["sala"]:
        return False
    if "tipo_providencia" in filtros and f.get("tipo_providencia") != filtros["tipo_providencia"]:
        return False
    anio = str(f.get("fecha") or "")[:4]
    if ("anio_desde" in filtros or "anio_hasta" in filtros) and not anio.isdigit():
        return False
    if "anio_desde" in filtros and int(anio) < filtros["anio_desde"]:
        return False
    return not ("anio_hasta" in filtros and int(anio) > filtros["anio_hasta"])
