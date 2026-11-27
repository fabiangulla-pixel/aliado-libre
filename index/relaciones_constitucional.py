"""«Cita a» y «es citada por» para las providencias de la Corte Constitucional.

Lo mismo que `index.providencias` hace con la Corte Suprema, para la otra
corte que más pregunta la gente (tutelas, salud, pensiones). Es lo más cerca
que se puede llegar, sin un modelo, a una línea jurisprudencial: ver qué
sentencias posteriores invocan una y en qué frase lo hacen.

Coincidencia de IDENTIFICADOR, no análisis jurídico: no dice si la sentencia
posterior reitera, cambia o se aparta del precedente, y la página lo advierte.

Construcción (`python -m index.relaciones_constitucional --construir`, ~2 min):
lee los dos crudos de la Corte (síntesis y texto completo), saca la forma
canónica de cada providencia («T-760/08») y busca en cada texto las citas a
otras. Estados como en la Suprema: «confirmada» (una sola providencia del
índice con ese identificador), «ambigua» (varias) o «no_resuelta» (no está
en el índice). Se ignora la que se nombra a sí misma (el encabezado).

Límite conocido: de las 37.824 providencias, ~25.700 solo tienen la síntesis
de la relatoría, que cita poco; las «citada por» se apoyan sobre todo en las
12.094 con texto completo. No se leen todavía las citas desde la Corte
Suprema ni el Consejo de Estado.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RAW = (
    RAIZ / "data" / "raw" / "corte_constitucional.json",
    RAIZ / "data" / "raw" / "corte_constitucional_texto.json",
)
RELACIONES = Path(
    os.environ.get("ALIADO_RELACIONES_CONSTITUCIONAL", RAIZ / "index" / "relaciones_constitucional.db")
)
PREFIJO = "corte_constitucional:"
ANIO_MIN = 1992

# «T-760/08», «C-355 de 2006», «SU.214/16», «A-004/09». Exige separador después
# de la letra o la palabra «sentencia»/«auto» antes: «T 2» suelto es prosa.
_RE_LETRA = re.compile(
    r"(?<![A-Za-z0-9])(SU|C|T|A)(\s*[.-]\s*|\s+)(\d{1,4})\s*(?:/|-|\s+de\s+(?:\d{1,2}\s+de\s+\w+\s+de\s+)?)"
    r"\s*(\d{4}|\d{2})(?!\d)",
)
_RE_PALABRA_ANTES = re.compile(r"(sentencia|sentencias|auto|providencia)s?\s*(n[ºo°.]?\s*)?$", re.I)
# «Auto 004 de 2009», «auto n.º 092 de 2008»
_RE_AUTO = re.compile(
    r"\bauto\s+(?:n[ºo°.]?\s*|No\.?\s*)?(\d{1,4})\s*(?:/|-|\s+de\s+)\s*(\d{4}|\d{2})(?!\d)", re.I
)


def _anio(a: str) -> int:
    n = int(a)
    if len(a) == 2:
        n = 1900 + n if n >= 50 else 2000 + n
    return n


def _canonica(letra: str, numero: str, anio: str) -> str | None:
    n = _anio(anio)
    if not (ANIO_MIN <= n <= _dt.date.today().year) or int(numero) == 0:
        return None
    return f"{letra.upper()}-{str(int(numero)).zfill(3)}/{str(n)[-2:]}"


def canonica_de_identificador(identificador: str) -> str | None:
    """«A. 024/92\xa0» -> «A-024/92»; «T-615/92» -> «T-615/92»."""
    s = (identificador or "").replace("\xa0", " ").strip()
    m = _RE_LETRA.search(s)
    return _canonica(m.group(1), m.group(3), m.group(4)) if m else None


def referencias(texto: str) -> list[tuple[str, str, int, int]]:
    """[(canónica, como aparece, inicio, fin)] de las providencias de la Corte
    Constitucional citadas en el texto."""
    salida = []
    for m in _RE_LETRA.finditer(texto):
        if not m.group(2).strip() and not _RE_PALABRA_ANTES.search(texto[max(0, m.start() - 25) : m.start()]):
            continue
        c = _canonica(m.group(1), m.group(3), m.group(4))
        if c:
            salida.append((c, m.group(0), m.start(), m.end()))
    for m in _RE_AUTO.finditer(texto):
        c = _canonica("A", m.group(1), m.group(2))
        if c:
            salida.append((c, m.group(0), m.start(), m.end()))
    salida.sort(key=lambda x: x[2])
    return salida


def _contexto(texto: str, inicio: int, fin: int, ancho: int = 160) -> str:
    a, b = max(0, inicio - ancho), min(len(texto), fin + ancho)
    return re.sub(r"\s+", " ", ("…" if a else "") + texto[a:b] + ("…" if b < len(texto) else "")).strip()


def _leer_crudos(rutas) -> dict[str, dict]:
    """id -> {identificador, fecha, url, texto}; si un id aparece en los dos
    crudos se queda el texto más largo (el completo frente a la síntesis)."""
    docs: dict[str, dict] = {}
    for ruta in rutas:
        ruta = Path(ruta)
        if not ruta.exists():
            continue
        for x in json.loads(ruta.read_text(encoding="utf-8")):
            did = x.get("id") or ""
            if not did.startswith(PREFIJO):
                continue
            texto = x.get("texto") or ""
            previo = docs.get(did)
            if previo and len(previo["texto"]) >= len(texto):
                continue
            docs[did] = {
                "identificador": (x.get("identificador") or "").replace("\xa0", " ").strip(),
                "fecha": x.get("fecha") if x.get("fecha") not in (None, "None") else None,
                "url": x.get("url_original") or "",
                "texto": texto,
            }
    return docs


def construir(rutas=RAW, destino: Path = RELACIONES) -> dict:
    docs = _leer_crudos(rutas)
    por_canonica: dict[str, list[str]] = {}
    for did, d in docs.items():
        d["canonica"] = canonica_de_identificador(d["identificador"])
        if d["canonica"]:
            por_canonica.setdefault(d["canonica"], []).append(did)

    tmp = destino.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute(
        "create table docs (id text primary key, canonica text, identificador text, fecha text, url text)"
    )
    con.execute(
        "create table citas (origen text, canonica text, original text, estado text, destino text,"
        " veces integer, contexto text)"
    )
    con.executemany(
        "insert into docs values (?,?,?,?,?)",
        [(did, d["canonica"], d["identificador"], d["fecha"], d["url"]) for did, d in docs.items()],
    )
    filas = []
    for did, d in docs.items():
        vistas: dict[str, list] = {}
        for canon, original, ini, fin in referencias(d["texto"]):
            if canon == d["canonica"]:
                continue
            if canon in vistas:
                vistas[canon][5] += 1
                continue
            destinos = por_canonica.get(canon, [])
            estado = "confirmada" if len(destinos) == 1 else ("ambigua" if destinos else "no_resuelta")
            vistas[canon] = [
                did,
                canon,
                original,
                estado,
                destinos[0] if len(destinos) == 1 else None,
                1,
                _contexto(d["texto"], ini, fin),
            ]
        filas.extend(vistas.values())
    con.executemany("insert into citas values (?,?,?,?,?,?,?)", filas)
    con.execute("create index i_origen on citas(origen)")
    con.execute("create index i_destino on citas(destino)")
    con.execute("create index i_canonica on citas(canonica)")
    con.commit()
    con.close()
    tmp.replace(destino)
    return {
        "providencias": len(docs),
        "con_identificador": sum(1 for d in docs.values() if d["canonica"]),
        "relaciones": len(filas),
        "confirmadas": sum(f[3] == "confirmada" for f in filas),
        "ambiguas": sum(f[3] == "ambigua" for f in filas),
        "no_resueltas": sum(f[3] == "no_resuelta" for f in filas),
    }


def disponible(ruta: Path | None = None) -> bool:
    return (ruta or RELACIONES).exists()


def relaciones(documento_id: str, limite: int = 50, ruta: Path | None = None) -> dict | None:
    """Mismo formato que `providencias.relaciones`, o None si el documento no
    está en el catálogo de la Corte Constitucional."""
    ruta = ruta or RELACIONES
    if not ruta.exists():
        return None
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        fila = con.execute(
            "select canonica, identificador, fecha, url from docs where id=?", (documento_id,)
        ).fetchone()
        if fila is None:
            return None
        canon, identificador, fecha, url = fila
        sal = con.execute(
            "select canonica, original, estado, destino, veces, contexto from citas where origen=?"
            " order by veces desc, canonica limit ?",
            (documento_id, limite),
        ).fetchall()
        n_sal = con.execute("select count(*) from citas where origen=?", (documento_id,)).fetchone()[0]
        ent = con.execute(
            "select c.origen, c.original, c.estado, c.veces, c.contexto, d.identificador, d.fecha"
            " from citas c left join docs d on d.id = c.origen"
            " where c.destino=? or (c.canonica=? and c.estado='ambigua')"
            " order by d.fecha desc limit ?",
            (documento_id, canon, limite),
        ).fetchall()
        n_ent = con.execute(
            "select count(*) from citas where destino=? or (canonica=? and estado='ambigua')",
            (documento_id, canon),
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "providencia": {
            "documento_id": documento_id,
            "identificador": identificador,
            "fecha": fecha,
            "url": url,
        },
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
                "identificador": ident or o,
                "documento_id": o,
                "como_aparece": orig,
                "estado": e,
                "veces": v,
                "contexto": ctx,
                "fecha": f,
            }
            for o, orig, e, v, ctx, ident, f in ent
        ],
        "total_cita_a": n_sal,
        "total_citada_por": n_ent,
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:] == ["--construir"]:
        print(construir())
    else:
        print(referencias(" ".join(sys.argv[1:])))
