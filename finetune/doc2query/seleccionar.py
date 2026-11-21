"""Paso 1 de doc2query: los fragmentos a los que se les escribiran preguntas coloquiales.

Normas que consulta la gente de a pie (trabajo, familia, consumo, servicios
publicos, vivienda, salud, datos personales, transito, convivencia). La lista
se fijo A PRIORI por tema, sin mirar los bancos de medicion: elegirla por las
anclas del banco seria medir con trampa.

    .venv/Scripts/python.exe finetune/doc2query/seleccionar.py
    -> finetune/doc2query/fragmentos.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8")

from ingest.chunking import fragmentar  # noqa: E402
from ingest.schema import Documento  # noqa: E402

NORMAS = {
    # trabajo
    "DECRETO-2663-1950": "Codigo Sustantivo del Trabajo",
    "LEY-1010-2006": "acoso laboral",
    "LEY-1822-2017": "licencia de maternidad",
    "LEY-2101-2021": "reduccion de la jornada laboral",
    "LEY-789-2002": "empleo y proteccion social",
    "LEY-50-1990": "reforma laboral, cesantias",
    # familia, herencias, personas
    "LEY-84-1873": "Codigo Civil",
    "LEY-54-1990": "union marital de hecho",
    "LEY-979-2005": "union marital de hecho",
    "LEY-1098-2006": "Codigo de la Infancia y la Adolescencia",
    "LEY-1257-2008": "violencia contra la mujer",
    "LEY-1996-2019": "capacidad legal de personas con discapacidad",
    "LEY-311-1996": "registro de alimentantes morosos",
    # consumo, deudas, datos
    "LEY-1480-2011": "Estatuto del Consumidor",
    "LEY-1266-2008": "habeas data financiero, centrales de riesgo",
    "LEY-1581-2012": "proteccion de datos personales",
    "LEY-2300-2023": "horarios de cobranza",
    # servicios publicos y vivienda
    "LEY-142-1994": "servicios publicos domiciliarios",
    "LEY-820-2003": "arrendamiento de vivienda urbana",
    "LEY-675-2001": "propiedad horizontal",
    # salud y seguridad social
    "LEY-100-1993": "sistema de seguridad social",
    "LEY-1751-2015": "derecho fundamental a la salud",
    # Estado, derechos, convivencia, transito
    "LEY-1755-2015": "derecho de peticion",
    "DECRETO-2591-1991": "accion de tutela",
    "LEY-1801-2016": "Codigo de Policia y Convivencia",
    "LEY-769-2002": "Codigo Nacional de Transito",
    # --- ampliacion 21-nov-2026: mismos criterios (tema ciudadano, sin mirar los bancos) ---
    "LEY-1562-2012": "riesgos laborales, accidentes de trabajo",
    "LEY-1221-2008": "teletrabajo",
    "LEY-361-1997": "estabilidad laboral reforzada por discapacidad",
    "LEY-1636-2013": "proteccion al cesante",
    "LEY-1060-2006": "impugnacion de paternidad",
    "LEY-721-2001": "pruebas de paternidad",
    "LEY-294-1996": "violencia intrafamiliar",
    "LEY-25-1992": "divorcio y matrimonio civil",
    "LEY-1361-2009": "proteccion integral a la familia",
    "LEY-640-2001": "conciliacion",
    "LEY-1328-2009": "consumidor financiero, bancos",
    "LEY-1676-2013": "garantias mobiliarias, prendas",
    "LEY-1537-2012": "vivienda de interes social",
    "LEY-797-2003": "pensiones",
    "LEY-1122-2007": "sistema de salud, EPS",
    "LEY-1438-2011": "sistema de salud",
    "LEY-1616-2013": "salud mental",
    "LEY-1733-2014": "cuidados paliativos",
    "LEY-472-1998": "acciones populares y de grupo",
    "LEY-1620-2013": "convivencia escolar, matoneo",
    "LEY-115-1994": "educacion",
    "LEY-30-1992": "educacion superior",
    "LEY-84-1989": "proteccion animal",
    "LEY-1482-2011": "discriminacion",
    "LEY-1251-2008": "adulto mayor",
    "LEY-1618-2013": "derechos de personas con discapacidad",
    "LEY-1341-2009": "telecomunicaciones, celular e internet",
    "LEY-1258-2008": "sociedades SAS, emprendimiento",
    "LEY-1383-2010": "transito, multas",
    "LEY-1448-2011": "victimas del conflicto, restitucion de tierras",
    "LEY-1116-2006": "reorganizacion empresarial e insolvencia",
    "LEY-1437-2011": "tramites ante entidades publicas",
    "LEY-1712-2014": "transparencia y acceso a la informacion publica",
    "LEY-599-2000": "Codigo Penal, delitos",
    "LEY-906-2004": "Codigo de Procedimiento Penal, denuncias",
    "LEY-1564-2012": "Codigo General del Proceso, demandas, insolvencia de persona natural",
    "DECRETO-410-1971": "Codigo de Comercio, negocios",
    "DECRETO-624-1989": "Estatuto Tributario, impuestos de personas",
}

# Las que no estan en legalize_co se toman del Gestor Normativo (Funcion Publica).
GESTOR = {
    "gestor_normativo:2752": "servicios publicos domiciliarios (Ley 142 de 1994)",
    "gestor_normativo:80538": "Codigo de Policia y Convivencia (Ley 1801 de 2016)",
    "gestor_normativo:99712": "capacidad legal de personas con discapacidad (Ley 1996 de 2019)",
    "gestor_normativo:60733": "derecho fundamental a la salud (Ley 1751 de 2015)",
    "gestor_normativo:65334": "derecho de peticion (Ley 1755 de 2015)",
    "gestor_normativo:78833": "licencia de maternidad (Ley 1822 de 2017)",
    "gestor_normativo:166506": "reduccion de la jornada laboral (Ley 2101 de 2021)",
    "gestor_normativo:213990": "horarios de cobranza (Ley 2300 de 2023)",
    # --- ampliacion 21-nov-2026 ---
    "gestor_normativo:162970": "trabajo en casa (Ley 2088 de 2021)",
    "gestor_normativo:167966": "trabajo remoto (Ley 2121 de 2021)",
    "gestor_normativo:260676": "reforma laboral (Ley 2466 de 2025)",
    "gestor_normativo:167967": "licencia de paternidad (Ley 2114 de 2021)",
    "gestor_normativo:82756": "trabajo nocturno (Ley 1846 de 2017)",
    "gestor_normativo:166186": "deudores alimentarios morosos REDAM (Ley 2097 de 2021)",
    "gestor_normativo:168066": "comisarias de familia (Ley 2126 de 2021)",
    "gestor_normativo:188766": "conciliacion (Ley 2220 de 2022)",
    "gestor_normativo:173246": "borron y cuenta nueva, reportes negativos (Ley 2157 de 2021)",
    "gestor_normativo:78234": "vivienda nueva, constructoras (Ley 1796 de 2016)",
    "gestor_normativo:246356": "reforma pensional (Ley 2381 de 2024)",
    "gestor_normativo:173788": "SOAT y transito (Ley 2161 de 2021)",
    "gestor_normativo:68135": "maltrato animal (Ley 1774 de 2016)",
    "gestor_normativo:187626": "justicia virtual (Ley 2213 de 2022)",
    "gestor_normativo:160966": "emprendimiento (Ley 2069 de 2020)",
}

MINIMO_CARACTERES = 120  # fragmentos de puro encabezado no merecen preguntas


def main() -> None:
    docs = json.loads((RAIZ / "data/raw/legalize_co_github.json").read_text(encoding="utf-8"))
    por_id = {}
    for d in docs:
        clave = d["id"].split(":", 1)[-1]
        if clave in NORMAS:
            por_id[clave] = d
    faltan = sorted(set(NORMAS) - set(por_id))
    temas = dict(NORMAS)
    for d in json.loads((RAIZ / "data/raw/gestor_normativo.json").read_text(encoding="utf-8")):
        if d["id"] in GESTOR:
            por_id[d["id"]] = d
            temas[d["id"]] = GESTOR[d["id"]]
    salida = RAIZ / "finetune/doc2query/fragmentos.jsonl"
    total = 0
    with salida.open("w", encoding="utf-8") as f:
        for clave in temas:
            d = por_id.get(clave)
            if not d:
                continue
            frags = [fr for fr in fragmentar(Documento(**d)) if len(fr.texto) >= MINIMO_CARACTERES]
            for fr in frags:
                f.write(
                    json.dumps(
                        {
                            "id": fr.id,
                            "documento_id": fr.documento_id,
                            "tema": temas[clave],
                            "titulo": fr.titulo_documento,
                            "texto": fr.texto,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            total += len(frags)
            print(f"{clave:20} {len(frags):>6} fragmentos")
    print(f"TOTAL {total} fragmentos -> {salida}")
    if faltan:
        print("No estan en legalize_co:", faltan)


if __name__ == "__main__":
    main()
