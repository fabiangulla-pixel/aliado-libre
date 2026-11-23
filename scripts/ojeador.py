"""OJEADOR (Corte Suprema) como referencia OPCIONAL: verificar enlaces y medir cobertura.

Nada de esto corre solo ni lo necesita la app: Aliado Libre funciona sin red.
Son herramientas para quien mantiene el índice, que se lanzan a mano.

Qué se sabe del servicio (comprobado el 23-nov-2026, ver docs/OJEADOR.md):
- El buscador ojeador.cortesuprema.gov.co consulta un servicio de la Corte
  (buscadorjurisprudenciabackend.cortesuprema.gov.co) SIN documentación pública:
  su /docs responde 401. No hay términos de uso que autoricen la descarga
  masiva; tampoco robots.txt. Se trata como interfaz no garantizada: puede
  cambiar sin aviso y estos scripts fallar sin que la app se entere.
- Por eso: pocas peticiones, una a la vez, con pausa (por defecto 3 s), un
  User-Agent que se identifica, y alto inmediato ante 429 o 403. No se
  envían consultas de usuarios: solo números de providencia del propio índice.

Subcomandos:

  verificar  Confirma en Ojeador providencias del índice por su número exacto
             (búsqueda estructurada Numerador = X). Escribe data/ojeador/
             verificacion.jsonl, que `index/providencias.py` lee para ofrecer
             el enlace a la ficha oficial SOLO si hubo una coincidencia clara.
               python scripts/ojeador.py verificar SL131-2026 SC10223-2014
               python scripts/ojeador.py verificar --muestra 40 --semilla 7

  muestrear  Toma una muestra de la fuente oficial (páginas al azar de una
             sala y un periodo) y la guarda con su metodología.
               python scripts/ojeador.py muestrear --sala LABORAL --desde 2025-01-01 \\
                   --hasta 2025-12-31 --paginas 3 --semilla 11

  comparar   Sin red. Compara una muestra (la de `muestrear`, o un JSON/CSV
             armado a mano con al menos la columna Numerador) contra el
             catálogo local y escribe un informe .md y un .json.
               python scripts/ojeador.py comparar data/ojeador/muestra_....json
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from index import providencias as P  # noqa: E402

SERVICIO = "https://buscadorjurisprudenciabackend.cortesuprema.gov.co"
CARPETA = RAIZ / "data" / "ojeador"
USER_AGENT = "AliadoLibre/verificacion (software libre; consultas espaciadas)"
CABECERAS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://ojeador.cortesuprema.gov.co",
    "Referer": "https://ojeador.cortesuprema.gov.co/",
    "Accept": "application/json",
}
CAMPOS = (
    "id",
    "Hash",
    "CUI",
    "Ubicacion",
    "Numerador",
    "FechaConsolidacionFirma",
    "Ponente",
    "TipoDeProvidencia",
    "Sala",
    "Especialidad",
    "ClaseActuacion",
    "TemaTexto",
)


class Detenido(RuntimeError):
    """El servicio pidió parar (429/403) o no responde: no se insiste."""


def _get(sesion, ruta: str, params: dict, pausa: float) -> dict:
    import requests

    time.sleep(pausa)
    try:
        r = sesion.get(SERVICIO + ruta, params=params, headers=CABECERAS, timeout=40)
    except requests.RequestException as e:
        raise Detenido(f"sin respuesta del servicio: {type(e).__name__}") from e
    if r.status_code in (403, 429):
        raise Detenido(f"el servicio respondió {r.status_code}: se detiene sin reintentar")
    r.raise_for_status()
    return r.json()


def _resumen(doc: dict) -> dict:
    return {k: doc.get(k) for k in CAMPOS}


def clasificar(canonica: str, resultados: list[dict]) -> tuple[str, dict | None]:
    """verificada | ambigua | no_encontrada. Varias filas del MISMO archivo
    (Ojeador indexa a veces la misma providencia dos veces) cuentan como una."""
    exactas = [d for d in resultados if P.canonica(str(d.get("Numerador") or "")) == canonica]
    if not exactas:
        return "no_encontrada", None
    if len({d.get("Ubicacion") for d in exactas}) == 1:
        return "verificada", exactas[0]
    return "ambigua", None


def verificar(numeradores: list[str], pausa: float) -> list[dict]:
    import requests

    CARPETA.mkdir(parents=True, exist_ok=True)
    sesion = requests.Session()
    salida = []
    with (CARPETA / "verificacion.jsonl").open("a", encoding="utf-8") as fh:
        for n in numeradores:
            canon = P.canonica(n)
            if not canon:
                print(f"  {n}: no es un identificador válido de la Suprema, se omite")
                continue
            params = {
                "query_text": "",
                "field": "Numerador",
                "term": n,
                "match": "equals",
                "limit": 10,
                "page": 1,
            }
            try:
                datos = _get(sesion, "/search/", params, pausa)
            except Detenido as e:
                print(f"DETENIDO en {n}: {e}")
                break
            estado, doc = clasificar(canon, datos.get("results") or [])
            fila = {
                "canonica": canon,
                "numerador": (doc or {}).get("Numerador") or n,
                "estado": estado,
                "hash": (doc or {}).get("Hash"),
                "id_ojeador": (doc or {}).get("id"),
                "ubicacion": (doc or {}).get("Ubicacion"),
                "fecha": ((doc or {}).get("FechaConsolidacionFirma") or "")[:10] or None,
                "cui": (doc or {}).get("CUI"),
                "clase_actuacion": (doc or {}).get("ClaseActuacion"),
                "tema": (doc or {}).get("TemaTexto"),
                "filas_en_ojeador": len(datos.get("results") or []),
                "consultado": _dt.datetime.now().isoformat(timespec="seconds"),
                "metodo": "GET /search/ field=Numerador match=equals",
            }
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            fh.flush()
            salida.append(fila)
            print(f"  {n}: {estado}")
    return salida


def contrastar(verificadas: list[dict]) -> dict:
    """Lo que el catálogo dedujo del texto frente a lo que publica la Corte."""
    cmp = Counter()
    for v in verificadas:
        if v["estado"] != "verificada":
            continue
        for did in P.documentos_de(v["canonica"]):
            f = P.catalogo()["documentos"][did]
            if f.get("fecha_precision") == "dia" and v.get("fecha"):
                cmp["fecha_comparable"] += 1
                cmp["fecha_igual"] += f["fecha"] == v["fecha"]
            if f.get("radicado_tipo") == "cui" and v.get("cui"):
                cmp["radicado_comparable"] += 1
                cmp["radicado_igual"] += f["radicado"].replace("-", "") == v["cui"]
    return dict(cmp)


def muestrear(
    sala: str, desde: str, hasta: str, paginas: int, por_pagina: int, semilla: int, pausa: float
) -> Path:
    import requests

    sesion = requests.Session()
    base = {
        "query_text": "",
        "especialidad": sala,
        "fechaInicio": desde,
        "fechaFin": hasta,
        "orden": "recientes",
        "limit": por_pagina,
    }
    primera = _get(sesion, "/search/", {**base, "page": 1}, pausa)
    total = int(primera.get("paginable_documents") or primera.get("total_documents") or 0)
    n_paginas = max(1, math.ceil(total / por_pagina))
    elegidas = sorted(random.Random(semilla).sample(range(1, n_paginas + 1), min(paginas, n_paginas)))
    docs = []
    for p in elegidas:
        datos = primera if p == 1 else _get(sesion, "/search/", {**base, "page": p}, pausa)
        docs.extend(_resumen(d) for d in datos.get("results") or [])
    CARPETA.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA / f"muestra_{sala.lower()}_{desde}_{hasta}_s{semilla}.json"
    ruta.write_text(
        json.dumps(
            {
                "metodologia": {
                    "fuente": "OJEADOR, Corte Suprema de Justicia (servicio no documentado)",
                    "consultado": _dt.datetime.now().isoformat(timespec="seconds"),
                    "parametros": {**base, "paginas_elegidas": elegidas, "semilla": semilla},
                    "universo_declarado": total,
                    "diseno": (
                        f"{len(elegidas)} páginas al azar de {n_paginas} (orden: recientes). Es una "
                        "muestra por conglomerados: las providencias de una página son de fechas "
                        "vecinas, así que la incertidumbre real es mayor que la de una muestra simple."
                    ),
                },
                "documentos": docs,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"{len(docs)} providencias de {total} declaradas -> {ruta}")
    return ruta


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m), min(1.0, c + m)


def leer_muestra(ruta: Path) -> tuple[list[dict], dict]:
    if ruta.suffix.lower() == ".csv":
        with ruta.open(encoding="utf-8-sig") as fh:
            muestra = csv.DictReader(fh, delimiter=";" if ";" in fh.readline() else ",")
            fh.seek(0)
            filas = list(csv.DictReader(fh, delimiter=muestra.reader.dialect.delimiter))
        return filas, {"fuente": f"archivo manual {ruta.name}"}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if isinstance(datos, list):
        return datos, {"fuente": f"archivo manual {ruta.name}"}
    return datos.get("documentos") or [], datos.get("metodologia") or {}


def comparar(ruta: Path) -> dict:
    filas, metodo = leer_muestra(ruta)
    if not P.disponible():
        sys.exit("Falta el catálogo local: python -m index.providencias --construir")
    cat = P.catalogo()["documentos"]
    vistos: dict[str, list[dict]] = defaultdict(list)
    pendientes = []
    for f in filas:
        canon = P.canonica(str(f.get("Numerador") or f.get("numerador") or "").strip())
        if canon:
            vistos[canon].append(f)
        else:
            pendientes.append(f.get("Numerador") or f.get("numerador"))
    detalle, discrepancias = [], []
    por_grupo: dict[tuple, Counter] = defaultdict(Counter)
    for canon, apariciones in vistos.items():
        ref = P.referencias(canon)[0]
        docs = P.documentos_de(canon)
        f0 = apariciones[0]
        anio = str(f0.get("FechaConsolidacionFirma") or ref.anio)[:4]
        estado = {
            "identificada_en_la_fuente": True,
            "en_nuestro_catalogo": bool(docs),
            "con_texto": bool(docs),  # el catálogo solo tiene providencias con texto (>100 caracteres)
            "con_texto_ocr": any(cat[d]["origen_texto"] in ("ocr", "mixto") for d in docs),
        }
        for d in docs:
            nuestra_fecha = str(cat[d].get("fecha") or "")
            if cat[d].get("fecha_precision") == "dia" and f0.get("FechaConsolidacionFirma"):
                if nuestra_fecha != str(f0["FechaConsolidacionFirma"])[:10]:
                    discrepancias.append({"identificador": canon, "campo": "fecha", "nuestro": nuestra_fecha,
                                          "fuente": str(f0["FechaConsolidacionFirma"])[:10]})  # fmt: skip
            sala_fuente = str(f0.get("Sala") or f0.get("Especialidad") or "").capitalize()
            if sala_fuente and cat[d].get("sala") and sala_fuente != cat[d]["sala"]:
                discrepancias.append(
                    {
                        "identificador": canon,
                        "campo": "sala",
                        "nuestro": cat[d]["sala"],
                        "fuente": sala_fuente,
                    }
                )
        detalle.append(
            {"identificador": canon, "repeticiones_en_muestra": len(apariciones), "anio": anio, **estado}
        )
        g = por_grupo[(ref.sala, ref.tipo, anio)]
        g["en_la_fuente"] += 1
        g["en_nuestro_catalogo"] += estado["en_nuestro_catalogo"]
        g["con_texto_ocr"] += estado["con_texto_ocr"]
    n = len(detalle)
    k = sum(d["en_nuestro_catalogo"] for d in detalle)
    lo, hi = _wilson(k, n)
    informe = {
        "metodologia": metodo,
        "muestra": str(ruta),
        "comparado": _dt.datetime.now().isoformat(timespec="seconds"),
        "catalogo_local": P.catalogo().get("generado"),
        "filas_leidas": len(filas),
        "identificadores_distintos": n,
        "duplicados_en_la_fuente": {c: len(a) for c, a in vistos.items() if len(a) > 1},
        "pendientes_de_comprobar": pendientes,
        "en_nuestro_catalogo": k,
        "proporcion_en_muestra": round(k / n, 4) if n else None,
        "intervalo_95_wilson_si_fuera_aleatoria_simple": [round(lo, 4), round(hi, 4)],
        "por_sala_tipo_anio": [
            {"sala": s, "tipo": t, "anio": a, **dict(c)} for (s, t, a), c in sorted(por_grupo.items())
        ],
        "discrepancias": discrepancias,
        "detalle": detalle,
    }
    base = ruta.with_name(ruta.stem + "_cobertura")
    base.with_suffix(".json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    base.with_suffix(".md").write_text(_markdown(informe), encoding="utf-8")
    print(_markdown(informe))
    return informe


def _markdown(i: dict) -> str:
    m = i["metodologia"] or {}
    lineas = [
        "# Cobertura de la Corte Suprema: muestra oficial frente al índice local",
        "",
        f"- Muestra: `{i['muestra']}` — {m.get('fuente', '')}, consultada {m.get('consultado', '¿?')}",
        f"- Diseño: {m.get('diseno', 'no declarado (archivo manual)')}",
        f"- Catálogo local generado: {i['catalogo_local']}; comparado {i['comparado']}",
        f"- Filas leídas {i['filas_leidas']}; identificadores distintos {i['identificadores_distintos']}; "
        f"duplicados en la fuente {len(i['duplicados_en_la_fuente'])}; "
        f"pendientes de comprobar (número no reconocido) {len(i['pendientes_de_comprobar'])}",
        "",
        f"**En nuestro catálogo: {i['en_nuestro_catalogo']} de {i['identificadores_distintos']}**"
        + (
            f" ({i['proporcion_en_muestra']:.0%} de esta muestra)."
            if i["proporcion_en_muestra"] is not None
            else "."
        ),
        "",
        "Vale para esta muestra. El intervalo "
        f"{i['intervalo_95_wilson_si_fuera_aleatoria_simple']} solo sería válido para una muestra aleatoria "
        "simple; con páginas al azar (conglomerados) la incertidumbre es mayor. No extrapolar a otras "
        "salas, años o tipos que la muestra no cubre.",
        "",
        "| Sala | Tipo | Año | En la fuente | En nuestro catálogo | Con texto OCR |",
        "|---|---|---|---|---|---|",
    ]
    for g in i["por_sala_tipo_anio"]:
        lineas.append(
            f"| {g['sala']} | {g['tipo']} | {g['anio']} | {g.get('en_la_fuente', 0)} | "
            f"{g.get('en_nuestro_catalogo', 0)} | {g.get('con_texto_ocr', 0)} |"
        )
    if i["discrepancias"]:
        lineas += ["", "## Discrepancias de identificación", ""]
        lineas += [f"- {d['identificador']}: {d['campo']} nuestro {d['nuestro']} / fuente {d['fuente']}"
                   for d in i["discrepancias"]]  # fmt: skip
    return "\n".join(lineas) + "\n"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="accion", required=True)
    v = sub.add_parser("verificar")
    v.add_argument("numeradores", nargs="*")
    v.add_argument("--muestra", type=int, default=0, help="N providencias al azar del catálogo local")
    v.add_argument("--semilla", type=int, default=7)
    v.add_argument("--pausa", type=float, default=3.0)
    m = sub.add_parser("muestrear")
    m.add_argument("--sala", required=True, help="LABORAL, CIVIL, PENAL…")
    m.add_argument("--desde", required=True)
    m.add_argument("--hasta", required=True)
    m.add_argument("--paginas", type=int, default=3)
    m.add_argument("--por-pagina", type=int, default=50)
    m.add_argument("--semilla", type=int, default=11)
    m.add_argument("--pausa", type=float, default=3.0)
    c = sub.add_parser("comparar")
    c.add_argument("muestra", type=Path)
    a = ap.parse_args()
    if a.accion == "verificar":
        nums = list(a.numeradores)
        if a.muestra:
            todos = sorted(
                f["numerador"] for f in P.catalogo().get("documentos", {}).values() if f.get("canonica")
            )
            nums += random.Random(a.semilla).sample(todos, min(a.muestra, len(todos)))
        filas = verificar(nums, max(a.pausa, 1.0))
        print(Counter(f["estado"] for f in filas), contrastar(filas))
    elif a.accion == "muestrear":
        muestrear(a.sala, a.desde, a.hasta, a.paginas, a.por_pagina, a.semilla, max(a.pausa, 1.0))
    else:
        comparar(a.muestra)


if __name__ == "__main__":
    main()
