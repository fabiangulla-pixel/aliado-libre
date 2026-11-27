"""Resuelve una cita exacta contra el corpus, sin pasar por la búsqueda.

`index/citas.py` reconoce la cita; aquí se traduce a documentos del índice
(catálogo construido una vez desde los metadatos de Chroma) y, si la cita trae
artículo, se busca el fragmento que lo contiene.

Reglas heredadas de Normativa-colombiana-MCP (ver index/citas.py):
- Cita SIN año y varios años posibles ("Decreto 1072"): no se elige en
  silencio; se devuelven los candidatos y se avisa.
- Si la cita no está en el corpus, se dice así ("no está en el índice"), que no
  es lo mismo que "la norma no existe".

Uso:
    .venv/Scripts/python.exe index/resolver_citas.py --construir      # catálogo
    .venv/Scripts/python.exe index/resolver_citas.py "art. 64 del CST"
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from index.citas import Cita, parsear_cita, sin_tildes  # noqa: E402

CATALOGO = RAIZ / "index" / "catalogo_citas.json"
MAX_FRAGMENTOS_DOC = 4000  # un código entero cabe; evita traer un documento absurdo

# legalize_co_github:LEY-1480-2011, DECRETO-LEY-019-2012, ACTO-LEGISLATIVO-1-2005
_RE_ID_LEGALIZE = re.compile(r"^([A-Z]+(?:-[A-Z]+)*)-(\d+)-(\d{4})$")
_RE_CONSTITUCION_TITULO = re.compile(r"^constituci[oó]n pol[ií]tica", re.I)


def clave(cita: Cita) -> str:
    if cita.sentencia:
        return "sentencia|" + cita.sentencia
    return f"{cita.tipo}|{cita.numero}|{cita.anio or ''}"


def clave_sin_anio(cita: Cita) -> str:
    return f"{cita.tipo}|{cita.numero}|"


def _cita_de_documento(documento_id: str, titulo: str) -> Cita | None:
    """La cita que identifica a un documento del corpus, desde su id o su título."""
    if documento_id.startswith("legalize_co_github:CONSTITUCION"):
        # CONSTITUCION-POLITICA-CP-1886-1886: solo la de 1991 es "la Constitución".
        return Cita("constitucion politica", "1", "1991") if documento_id.endswith("-1991") else None
    if documento_id.startswith("legalize_co_github:"):
        m = _RE_ID_LEGALIZE.match(documento_id.split(":", 1)[1])
        if not m:
            return None
        tipo = m.group(1).replace("-", " ").lower()
        return parsear_cita(f"{tipo} {int(m.group(2))} de {m.group(3)}")
    if _RE_CONSTITUCION_TITULO.match(titulo or ""):
        anios = set(re.findall(r"\b(1[89]\d\d|20\d\d)\b", titulo))
        return Cita("constitucion politica", "1", "1991") if anios <= {"1991"} else None
    if documento_id.startswith(("corte_constitucional:", "dian:", "gestor_normativo:")):
        # Solo el comienzo del título: más adelante suelen citarse OTRAS normas
        # ("Decreto 821 de 2022, que modifica la Ley 909 de 2004"). 80, no 60:
        # con 60 un título largo cortaba el año a mitad camino ("...de 202")
        # y el parser lo leía como año "02" (SU-499/02 en vez de SU-499/24).
        return parsear_cita((titulo or "")[:80])
    return None


def construir_catalogo(ruta_sqlite: Path | None = None) -> dict:
    """Lee los metadatos de Chroma directamente (solo lectura) y escribe el catálogo."""
    from index.buscar import DIR_INDICE

    ruta = ruta_sqlite or Path(DIR_INDICE) / "chroma.sqlite3"
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    filas = con.execute(
        """select a.string_value, b.string_value from embedding_metadata o
           join embedding_metadata a on a.id = o.id and a.key = 'documento_id'
           join embedding_metadata b on b.id = o.id and b.key = 'titulo_documento'
           where o.key = 'orden' and o.int_value = 0"""
    ).fetchall()
    con.close()

    exacto: dict[str, list[str]] = defaultdict(list)
    sin_anio: dict[str, list[str]] = defaultdict(list)
    titulos: dict[str, str] = {}
    for documento_id, titulo in filas:
        cita = _cita_de_documento(documento_id, titulo)
        if cita is None:
            continue
        exacto[clave(cita)].append(documento_id)
        if not cita.sentencia:
            sin_anio[clave_sin_anio(cita)].append(documento_id)
        titulos[documento_id] = titulo
    catalogo = {
        "documentos_leidos": len(filas),
        "exacto": exacto,
        "sin_anio": sin_anio,
        "titulos": titulos,
    }
    CATALOGO.write_text(json.dumps(catalogo, ensure_ascii=False), encoding="utf-8")
    return catalogo


_cache: dict | None = None


def catalogo() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(CATALOGO.read_text(encoding="utf-8")) if CATALOGO.exists() else {}
    return _cache


def anio_de_documento(documento_id: str, titulo: str) -> str:
    """Año de una norma: del título («Decreto 1072 de 2015») o del id con forma
    TIPO-NUM-AAAA. Nunca de los últimos cuatro dígitos de cualquier id: los del
    Gestor son numéricos («gestor_normativo:5343») y se leían como el año 5343
    (encontrado el 27-nov-2026 en los candidatos de «Decreto 1072»)."""
    m = re.search(r"\bde\s+(\d{4})\b", titulo or "") or re.search(r"-(\d{4})$", documento_id)
    if m and 1800 <= int(m.group(1)) <= 2100:
        return m.group(1)
    return "?"


@dataclass
class Resolucion:
    cita: Cita | None
    resultados: list[dict] = field(default_factory=list)
    aviso: str = ""
    candidatos: list[dict] = field(default_factory=list)  # cita sin año con varios años


def _re_articulo(articulo: str) -> re.Pattern:
    num = re.escape(articulo)
    # "ARTÍCULO 64.", "Artículo 64o", "Art. 64": no casa con "64-1" ni "640".
    # "\S{1,3}" tolera el texto con doble codificación de 64 documentos del
    # Gestor ("ARTÃ\x8dCULO"): medido el 3-oct-2026, 28.373 fragmentos.
    return re.compile(rf"\bart(?:\S{{1,3}}culo|\.)?\s*{num}(?![\d-])", re.I)


def _fragmentos(coleccion, documento_id: str) -> list[dict]:
    datos = coleccion.get(
        where={"documento_id": documento_id},
        include=["documents", "metadatas"],
        limit=MAX_FRAGMENTOS_DOC,
    )
    frags = [
        {"id": i, "texto": t, **(m or {})}
        for i, t, m in zip(datos["ids"], datos["documents"], datos["metadatas"], strict=True)
    ]
    return sorted(frags, key=lambda f: f.get("orden", 0))


_RE_RADICADO_INTERNO = re.compile(
    r"\brad(?:icado|icaci[oó]n|\.)\s*(?:n(?:[uú]mero|o|\.)?\s*[°º]?\s*\.?\s*)?:?\s*(\d{4,7})(?![\d-])", re.I
)


def _resolver_suprema(texto: str, coleccion, k: int) -> Resolucion | None:
    """Providencias de la Corte Suprema por identificador (SL131-2026) o radicado.

    Identificador y radicado son cosas distintas: el identificador nombra LA
    providencia; el radicado nombra el PROCESO, que puede tener varias. None si
    el texto no trae ninguno de los dos (sigue la resolución de normas)."""
    from index import providencias as P
    from index.citas import parsear_radicado
    from index.vigencia import anotar

    ref = P.parsear(texto)
    ant = P.parsear_antigua(texto)
    if ref is not None and not ref.completa and ant is not None and ant.identificador:
        ref = None  # «CSJ SC1171, 8 abr. 2022»: el año lo trae la fecha
    docs: list[str] = []
    aviso = ""
    if ref is not None:
        cita = Cita(tipo=ref.tipo, numero=str(ref.numero), anio=ref.anio, sentencia=ref.canonica)
        if not P.disponible():
            return Resolucion(
                cita,
                aviso="Falta el catálogo de la Corte Suprema (python -m index.providencias --construir).",
            )
        if not ref.completa:
            pref = ref.canonica + "-"
            cands = sorted(c for c in P.catalogo().get("por_canonica", {}) if c.startswith(pref))
            if not cands:
                return Resolucion(
                    cita, aviso=f"«{ref.original}» no trae año y no hay ninguna {ref.canonica} en el índice."
                )
            if len(cands) > 1:
                return Resolucion(
                    cita,
                    aviso=f"«{ref.original}» no trae año y hay {len(cands)} providencias con ese número. "
                    "¿De qué año?",
                    candidatos=[
                        {"anio": c.rsplit("-", 1)[1], "documento_id": P.documentos_de(c)[0], "titulo": c}
                        for c in cands
                    ],
                )
            docs = P.documentos_de(cands[0])
            aviso = f"«{ref.original}» no trae año; la única en el índice es {cands[0]}."
        else:
            docs = P.documentos_de(ref.canonica)
            if len(docs) > 1:
                aviso = f"Hay {len(docs)} documentos con el identificador {ref.canonica}: revisa cuál es."
        if not docs:
            return Resolucion(
                cita,
                aviso=f"La providencia {ref.canonica} no está en el índice (no quiere decir que no exista). "
                "Puedes buscarla en Ojeador, el buscador oficial de la Corte Suprema.",
            )
    elif ant is not None and P.disponible():
        # cita antigua: «CSJ SL, 5 ago. 2014, rad. 45678». Fecha y radicado
        # juntos identifican la decisión; solo la fecha, o solo el año, no.
        cita = Cita(tipo="sentencia", numero=ant.radicado or "", anio=ant.fecha[:4], sentencia=ant.etiqueta)
        documentos = P.catalogo().get("documentos", {})
        docs = P.candidatos_antigua(ant, documentos)
        if not docs:
            return Resolucion(
                cita,
                aviso=f"«{ant.original}»: no hay en el índice una providencia de la Corte Suprema con "
                + ("ese radicado y esa fecha" if ant.radicado else "esa fecha")
                + " (no quiere decir que no exista). Puedes buscarla en Ojeador.",
            )
        if len(docs) > 1:
            aviso = (
                f"«{ant.original}» coincide con {len(docs)} providencias del índice"
                + ("" if ant.radicado else " de esa fecha")
                + ": revisa cuál es."
            )
        elif ant.identificador and documentos[docs[0]].get("canonica") == ant.identificador:
            pass  # «CSJ SC1171, 8 abr. 2022»: número y año la identifican
        elif documentos[docs[0]].get("fecha") != ant.fecha:
            aviso = (
                f"«{ant.original}»: coincide el radicado y el año, pero el índice no tiene la fecha "
                "completa de esta providencia: confírmala antes de citarla."
            )
        elif not ant.radicado:
            aviso = (
                f"«{ant.original}» no trae radicado: es la única del índice con esa fecha, "
                "pero puede haber otras."
            )
    else:
        rad = parsear_radicado(texto)
        if rad and rad.corporacion == "consejo-de-estado":
            return None  # no es de la Suprema: no se le responde con la Suprema
        m = None if rad else _RE_RADICADO_INTERNO.search(texto)
        if not rad and not m:
            return None
        if not P.disponible():
            return None
        buscado = rad.formateado if rad else m.group(1)
        cita = Cita(tipo="radicado", numero=buscado)
        docs = [d for d, f in P.catalogo().get("documentos", {}).items() if f.get("radicado") == buscado]
        if not docs:
            return Resolucion(
                cita, aviso=f"No hay providencias de la Corte Suprema con el radicado {buscado} en el índice."
            )
        if len(docs) > 1:
            aviso = (
                f"El radicado {buscado} corresponde a {len(docs)} providencias del índice: "
                "un radicado identifica el proceso, no una decisión."
            )
    salida: list[dict] = []
    for d in docs[:k]:
        salida.extend(_fragmentos(coleccion, d)[:1])
    for f in salida:
        f["puntaje"] = 1.0
        f["cita_exacta"] = True
    return Resolucion(cita, P.anotar(anotar(salida[:k])), aviso)


def resolver(texto: str, coleccion, k: int = 5) -> Resolucion:
    """Resuelve la cita de `texto` contra el corpus. Sin cita, devuelve Resolucion(None)."""
    from index.vigencia import anotar

    suprema = _resolver_suprema(texto, coleccion, k)
    if suprema is not None:
        return suprema
    cita = parsear_cita(texto)
    if cita is None:
        return Resolucion(None)
    cat = catalogo()
    if not cat:
        return Resolucion(cita, aviso="Falta el catálogo de citas (index/resolver_citas.py --construir).")

    docs = list(cat["exacto"].get(clave(cita), []))
    if not docs and not cita.anio and not cita.sentencia:
        docs_sin = cat["sin_anio"].get(clave_sin_anio(cita), [])
        anios = {}
        for d in docs_sin:
            anios.setdefault(anio_de_documento(d, cat["titulos"].get(d, "")), d)
        if len(anios) > 1:
            return Resolucion(
                cita,
                aviso=f"La cita no trae año y hay {len(anios)} normas con ese número. ¿De qué año?",
                candidatos=[
                    {"anio": a, "documento_id": d, "titulo": cat["titulos"].get(d, "")}
                    for a, d in sorted(anios.items())
                ],
            )
        docs = docs_sin
    if not docs:
        return Resolucion(cita, aviso="Esa norma no está en el índice (no quiere decir que no exista).")

    salida: list[dict] = []
    aviso = ""
    for d in docs:
        frags = _fragmentos(coleccion, d)
        if cita.articulo:
            patron = _re_articulo(cita.articulo)
            elegidos = [f for f in frags if patron.search(sin_tildes(f["texto"] or ""))]
            if not elegidos:
                aviso = (
                    "El documento está en el índice, pero no encontré el artículo "
                    f"{cita.articulo} en su texto."
                )
                elegidos = frags[:1]
        else:
            elegidos = frags[:1]
        salida.extend(elegidos[:2])
        if len(salida) >= k:
            break
    for f in salida:
        f["puntaje"] = 1.0
        f["cita_exacta"] = True
    return Resolucion(cita, anotar(salida[:k]), aviso)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:] == ["--construir"]:
        c = construir_catalogo()
        print(f"{c['documentos_leidos']} documentos; {len(c['exacto'])} citas exactas en el catálogo")
    else:
        import chromadb

        from index.buscar import COLECCION, DIR_INDICE

        col = chromadb.PersistentClient(path=str(DIR_INDICE)).get_collection(COLECCION)
        r = resolver(" ".join(sys.argv[1:]), col)
        print(r.cita, "|", r.aviso)
        for c in r.candidatos:
            print("  candidato:", c)
        for f in r.resultados:
            print(f"  {f['titulo_documento']} [{f['id']}]\n    {f['texto'][:200]!r}")
