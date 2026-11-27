"""Verificador de citas: «¿existen las normas y sentencias que cita este texto?»

La persona pega un texto que le llegó (la respuesta de una entidad, un escrito
que le redactaron, el mensaje de un abogado, la salida de una IA) y la app le
dice, cita por cita, si está en el índice, si tiene nota de que no rige y dónde
leerla. JuridAI y Lexivox lo ofrecen a abogados (27-nov-2026); aquí es gratis y
sin IA.

Reglas (las de siempre del proyecto):

- **«No está en el índice» no es «no existe».** Se dice tal cual, con lo que
  falta del índice. Una norma reciente o una sentencia que la Corte aún no
  publicó pueden no estar.
- **Sin año y con varios años posibles, no se elige**: se listan los candidatos.
- **Vigencia: solo estados negativos.** La tabla de vigencias dice cuándo hay
  nota de derogada, inexequible…; sin nota no se afirma que rija.
- **El artículo solo se comprueba si el índice local ya está cargado** (hace
  falta leer los fragmentos). Si no, se dice «artículo sin comprobar».

Determinista: reutiliza `index.citas` (normas, códigos, sentencias de la Corte
Constitucional), `index.providencias` (Corte Suprema) y la tabla de vigencias.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from index import citas as C

MAX_TEXTO = 30000
MAX_CITAS = 80

# «artículo 64 del», «art. 5 de la», «artículos 152 y siguientes de la»: el
# artículo va antes de la norma, a poca distancia y sin otra norma en medio.
_RE_ARTICULO_ANTES = re.compile(r"\bart(?:[íi]culos?|s?\.)\s*(\d+(?:-\d+)?[A-Za-z]?)\b[^.;\n]{0,45}$", re.I)
_RE_CONSTITUCION = re.compile(r"\bconstituci[oó]n\s+pol[ií]tica\b|\bCarta\s+Pol[ií]tica\b", re.I)
_TIPOS_NORMA = {"ley", "decreto", "decreto ley", "resolucion", "acto legislativo", "circular", "concepto"}

ESTADOS = ("en_indice", "no_en_indice", "sin_anio", "ambigua", "sin_catalogo")


@dataclass
class CitaVerificada:
    texto: str
    inicio: int
    fin: int
    clase: str  # norma | codigo | constitucion | sentencia_cc | providencia_csj
    reconocida: str
    articulo: str | None = None
    estado: str = "no_en_indice"
    documentos: list[dict] = field(default_factory=list)
    candidatos: list[dict] = field(default_factory=list)
    vigencia: dict | None = None
    articulo_comprobado: bool | None = None
    aviso: str = ""
    veces: int = 1

    def a_dict(self) -> dict:
        return dict(self.__dict__)


_RE_ARTICULO = re.compile(r"\bart(?:[íi]culos?|s?\.)\s*(\d+(?:-\d+)?[A-Za-z]?)\b", re.I)


def _articulo_antes(texto: str, inicio: int) -> str | None:
    """El artículo MÁS CERCANO antes de la norma: en «art. 140 de la Ley 142 y el
    art. 64 del CST», al CST le toca el 64."""
    ventana = texto[max(0, inicio - 70) : inicio]
    ultimos = list(_RE_ARTICULO.finditer(ventana))
    if not ultimos:
        return None
    m = ultimos[-1]
    return m.group(1) if _RE_ARTICULO_ANTES.search(ventana[m.start() :]) else None


def _anio_ok(a: str | None) -> bool:
    if a is None:
        return True
    import datetime as _dt

    return 1800 <= int(a) <= _dt.date.today().year + 1


def extraer(texto: str) -> list[CitaVerificada]:
    """Todas las citas reconocibles del texto, en orden, sin resolver aún.

    Los espacios se colapsan antes: un texto pegado parte «Código\\nSustantivo
    del Trabajo» en dos líneas. Las posiciones devueltas son las del texto
    colapsado (`verificar` lo devuelve también, para resaltar sobre él)."""
    texto = re.sub(r"\s+", " ", texto[:MAX_TEXTO])
    halladas: list[CitaVerificada] = []
    ocupado: list[tuple[int, int]] = []

    def libre(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in ocupado)

    def agregar(c: CitaVerificada) -> None:
        if libre(c.inicio, c.fin):
            ocupado.append((c.inicio, c.fin))
            halladas.append(c)

    # 1. Corte Suprema con identificador («SL131-2026») y citas antiguas («CSJ SL, 5 ago. 2014, rad. …»)
    from index import providencias as P

    for r in P.referencias(texto):
        agregar(CitaVerificada(r.original, r.inicio, r.fin, "providencia_csj", r.canonica))
    for r in P.referencias_antiguas(texto):
        if r.radicado or r.identificador:
            agregar(CitaVerificada(r.original, r.inicio, r.fin, "providencia_csj", r.etiqueta))

    # 2. Corte Constitucional («T-760/08», «sentencia C-355 de 2006»)
    for m in C._RE_SENTENCIA.finditer(texto):
        if not (m.group(2).strip() or C._RE_PALABRA_SENTENCIA.search(texto[: m.start()])):
            continue
        letra, num, a = m.group(1).upper(), m.group(3), m.group(4)
        anio = a if len(a) == 4 else C._expandir_anio(a)
        if not _anio_ok(anio) or int(anio) < 1992:
            continue
        agregar(
            CitaVerificada(
                m.group(0), m.start(), m.end(), "sentencia_cc", f"{letra}-{num.zfill(3)}/{anio[-2:]}"
            )
        )

    # 3. Constitución Política
    for m in _RE_CONSTITUCION.finditer(texto):
        agregar(
            CitaVerificada(
                m.group(0), m.start(), m.end(), "constitucion", "Constitución Política de 1991",
                articulo=_articulo_antes(texto, m.start()),
            )
        )  # fmt: skip

    # 4. Códigos por su nombre («Código Sustantivo del Trabajo», «CGP»)
    plano = C.sin_tildes(texto).lower()
    for m in C._RE_ALIAS.finditer(plano):
        cod = C._POR_ALIAS.get(m.group(1).lower())
        if cod:
            agregar(
                CitaVerificada(
                    texto[m.start() : m.end()], m.start(), m.end(), "codigo",
                    f"{cod.nombre} ({cod.tipo.capitalize()} {cod.numero} de {cod.anio})",
                    articulo=_articulo_antes(texto, m.start()),
                )
            )  # fmt: skip

    # 5. Normas por tipo y número («Ley 1480 de 2011», «Decreto 1072»)
    for m in C._RE_TIPO_NUM.finditer(texto):
        tipo = C._normaliza(m.group(1))
        if tipo not in _TIPOS_NORMA:
            continue
        bruto = m.group(3)
        anio = (bruto if len(bruto) == 4 else C._expandir_anio(bruto)) if bruto else None
        if not _anio_ok(anio):
            continue
        numero = str(int(m.group(2)))
        etiqueta = f"{tipo.capitalize()} {numero}" + (f" de {anio}" if anio else "")
        agregar(
            CitaVerificada(
                m.group(0), m.start(), m.end(), "norma", etiqueta, articulo=_articulo_antes(texto, m.start())
            )
        )

    halladas.sort(key=lambda c: c.inicio)
    # La misma cita repetida se cuenta una vez (con su número de apariciones).
    unicas: dict[tuple, CitaVerificada] = {}
    for c in halladas:
        k = (c.clase, c.reconocida, c.articulo)
        if k in unicas:
            unicas[k].veces += 1
        else:
            unicas[k] = c
    return list(unicas.values())[:MAX_CITAS]


# --- resolución --------------------------------------------------------------


def _url(documento_id: str) -> str:
    """Enlace oficial cuando el id lo permite. Sin adivinar los demás."""
    if documento_id.startswith("gestor_normativo:"):
        return (
            "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i="
            + documento_id.split(":", 1)[1]
        )
    return ""


def _vigencia(documentos: list[str]) -> dict | None:
    """El estado más grave de la tabla de vigencias entre los documentos."""
    from index.vigencia import INCIERTA, NO_VIGENTES, tabla

    peor = None
    for d in documentos:
        fila = tabla().get(d)
        if not fila:
            continue
        if fila["estado"] in NO_VIGENTES and fila.get("alcance") == "documento":
            return {**fila, "documento_id": d}
        if peor is None or (fila["estado"] != INCIERTA and peor["estado"] == INCIERTA):
            peor = {**fila, "documento_id": d}
    return peor


def _resolver_norma(c: CitaVerificada, cita: C.Cita, titulos_cc: dict | None = None) -> None:
    from index import resolver_citas as R

    cat = R.catalogo()
    if not cat:
        c.estado = "sin_catalogo"
        c.aviso = "Falta el catálogo de citas en este equipo: no se puede verificar."
        return
    docs = list(cat["exacto"].get(R.clave(cita), []))
    if not docs and not cita.anio and not cita.sentencia:
        sin = cat["sin_anio"].get(R.clave_sin_anio(cita), [])
        anios: dict[str, str] = {}
        for d in sin:
            anios.setdefault(R.anio_de_documento(d, cat["titulos"].get(d, "")), d)
        if len(anios) > 1:
            c.estado = "sin_anio"
            # Los más recientes primero: suelen ser los que se citan hoy.
            c.candidatos = [
                {"anio": a, "documento_id": d, "titulo": cat["titulos"].get(d, ""), "url": _url(d)}
                for a, d in sorted(anios.items(), reverse=True)
            ]
            c.aviso = f"La cita no trae año y hay {len(anios)} normas con ese número en el índice."
            return
        docs = sin
    if not docs:
        c.estado = "no_en_indice"
        c.aviso = "No está en el índice. No quiere decir que no exista: búscala en la fuente oficial."
        return
    c.estado = "en_indice"
    c.documentos = [{"id": d, "titulo": cat["titulos"].get(d, ""), "url": _url(d)} for d in docs[:4]]
    c.vigencia = _vigencia(docs)


def _resolver_csj(c: CitaVerificada) -> None:
    from index import providencias as P

    if not P.disponible():
        c.estado = "sin_catalogo"
        c.aviso = "Falta el catálogo de la Corte Suprema en este equipo: no se puede verificar."
        return
    ref = P.parsear(c.texto)
    if ref is not None and ref.completa:
        docs = P.documentos_de(ref.canonica)
    else:
        ant = P.parsear_antigua(c.texto)
        docs = P.candidatos_antigua(ant, P.catalogo().get("documentos", {})) if ant else []
    if not docs:
        c.estado = "no_en_indice"
        c.aviso = (
            "No está en el índice (el índice tiene sobre todo las salas Laboral y Civil con texto digital). "
            "Búscala en Ojeador, el buscador oficial de la Corte Suprema."
        )
        return
    c.estado = "en_indice" if len(docs) == 1 else "ambigua"
    if len(docs) > 1:
        c.aviso = f"Coincide con {len(docs)} providencias del índice: revisa cuál es."
    for d in docs[:4]:
        f = P.ficha(d) or {}
        enl = f.get("enlaces") or {}
        c.documentos.append(
            {
                "id": d,
                "titulo": " ".join(
                    x for x in (f.get("numerador"), f.get("tipo_providencia"), f.get("fecha")) if x
                ),
                "url": enl.get("ficha") or enl.get("buscar_en_ojeador") or "",
            }
        )


def _url_cc(documento_id: str) -> str:
    try:
        from index import relaciones_constitucional as rc

        rel = rc.relaciones(documento_id, limite=1)
        return (rel or {}).get("providencia", {}).get("url") or ""
    except Exception:  # noqa: BLE001 - el enlace es un extra
        return ""


def _comprobar_articulo(c: CitaVerificada, coleccion) -> None:
    """Con la colección local, busca el artículo en el texto de la norma."""
    if not c.articulo or not c.documentos or coleccion is None:
        return
    from index import resolver_citas as R

    patron = R._re_articulo(c.articulo)
    for d in c.documentos[:2]:
        try:
            frags = R._fragmentos(coleccion, d["id"])
        except Exception:  # noqa: BLE001
            return
        if any(patron.search(C.sin_tildes(f.get("texto") or "")) for f in frags):
            c.articulo_comprobado = True
            return
    c.articulo_comprobado = False
    c.aviso = (c.aviso + " " if c.aviso else "") + (
        f"La norma está, pero no encontré el artículo {c.articulo} en su texto: revisa el número."
    )


def verificar(texto: str, coleccion=None) -> dict:
    """{"citas": [...], "resumen": {...}, "recortado": bool}."""
    recortado = len(texto or "") > MAX_TEXTO
    halladas = extraer(texto or "")
    for c in halladas:
        if c.clase == "providencia_csj":
            _resolver_csj(c)
            continue
        if c.clase == "sentencia_cc":
            letra, resto = c.reconocida.split("-", 1)
            numero, yy = resto.split("/")
            cita = C.Cita(
                "auto" if letra == "A" else "sentencia", numero, C._expandir_anio(yy), sentencia=c.reconocida
            )
            _resolver_norma(c, cita)
            if c.estado == "no_en_indice":
                c.aviso = (
                    "No está en el índice. Puede ser muy reciente o no estar publicada aún en la relatoría: "
                    "búscala en el sitio de la Corte Constitucional."
                )
            for d in c.documentos:
                d["url"] = d["url"] or _url_cc(d["id"])
            continue
        if c.clase == "constitucion":
            cita = C.Cita("constitucion politica", "1", "1991")
        elif c.clase == "codigo":
            cod = C._POR_ALIAS[C.sin_tildes(c.texto).lower()]
            cita = C.Cita(cod.tipo, cod.numero, cod.anio)
        else:
            cita = C.parsear_cita(c.texto)
            if cita is None:
                continue
        _resolver_norma(c, cita)
        _comprobar_articulo(c, coleccion)
    resumen = {e: sum(1 for c in halladas if c.estado == e) for e in ESTADOS}
    resumen["no_rigen"] = sum(
        1
        for c in halladas
        if c.vigencia and c.vigencia.get("alcance") == "documento" and c.vigencia["estado"] != "incierta"
    )
    resumen["total"] = len(halladas)
    return {"citas": [c.a_dict() for c in halladas], "resumen": resumen, "recortado": recortado}
