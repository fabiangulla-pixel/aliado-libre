"""Providencias de la Corte Suprema: identificadores, ficha, enlaces, relaciones.

FIXTURES: las providencias "corte_suprema:*:SL99001-2026" y vecinas son
FICTICIAS (numeración que la Corte no ha usado), salvo donde se dice "real":
SL131-2026 existe y sus datos se compararon con Ojeador el 23-nov-2026.
"""

from __future__ import annotations

import json

import pytest

from index import providencias as P
from index import resolver_citas as rc

# --- reconocimiento -------------------------------------------------------


@pytest.mark.parametrize(
    "texto, canonica",
    [
        ("CSJ SL131-2026", "SL131-2026"),  # real
        ("sentencia SL 131-2026 de la Sala Laboral", "SL131-2026"),
        ("SL-131-2026", "SL131-2026"),
        ("SL131 de 2026", "SL131-2026"),
        ("SC016-2018", "SC16-2018"),  # el cero a la izquierda no distingue
        ("STC6026-2021", "STC6026-2021"),
        ("AC739-2026", "AC739-2026"),
        ("SP1291-2018", "SP1291-2018"),
        ("SL9A-2019", "SL9A-2019"),
        ("ATL5-2025", "ATL5-2025"),  # visto en la muestra oficial de Ojeador
        ("AHL1234-2025", "AHL1234-2025"),
        ("(CSJ SL1367-2024, SL131-2026).", "SL1367-2024"),
    ],
)
def test_reconoce_identificadores_validos(texto, canonica):
    assert P.referencias(texto)[0].canonica == canonica


@pytest.mark.parametrize(
    "texto",
    [
        "me pagaron al 12-2020 la prima",  # minúsculas: prosa, no un auto
        "SL131-1850",  # año imposible
        "SU-837-2002",  # Corte Constitucional: lo resuelve index/citas.py
        "T-760/08",
        "SLSL2574-2022",  # error tipográfico del corpus: no se adivina
        "XSL131-2026",
        "Ley 1480 de 2011",
    ],
)
def test_no_acepta_identificadores_ajenos_o_mal_formados(texto):
    assert P.referencias(texto) == []


def test_varias_referencias_en_orden():
    assert [r.canonica for r in P.referencias("CSJ SL817-2022 y STL10313-2017")] == [
        "SL817-2022",
        "STL10313-2017",
    ]


def test_referencia_incompleta_sin_anio():
    r = P.parsear("qué dijo la SL131 sobre esto")
    assert r is not None and not r.completa and r.canonica == "SL131"


def test_sala_y_tipo_por_prefijo():
    r = P.parsear("STC6026-2021")
    assert (r.sala, r.tipo) == ("Civil", "sentencia de tutela")
    assert P.parsear("AL5223-2025").tipo == "auto"


# --- metadatos del encabezado ---------------------------------------------

ENCABEZADO = (
    "MARJORIE ZÚÑIGA ROMERO\nMagistrada ponente\nSL131-2026\n"
    "Radicación n.° 08001-22-05-000-2024-00028-01\nActa 4\n"
    "Bogotá D. C., once (11) de febrero de dos mil veintiséis (2026)\nLa Sala decide"
)  # real (SL131-2026)


def test_fecha_completa_del_encabezado():
    assert P.fecha_del_encabezado(ENCABEZADO, "2026") == "2026-02-11"


def test_no_inventa_fecha():
    assert P.fecha_del_encabezado("Bogotá, 2026. La Sala decide", "2026") is None
    assert P.fecha_del_encabezado(ENCABEZADO, "2025") is None  # no concuerda con el año
    assert P.fecha_del_encabezado("treinta y uno (31) de febrero de dos mil veinte (2020)", "2020") is None


def test_radicado_unico_y_radicado_interno():
    assert P.radicado_del_encabezado(ENCABEZADO) == ("08001-22-05-000-2024-00028-01", "cui")
    assert P.radicado_del_encabezado("Radicación n.° 45678\nActa 12") == ("45678", "interno")
    assert P.radicado_del_encabezado("Radicado n. 42512 \nrecargos") == ("42512", "interno")
    assert P.radicado_del_encabezado("sin radicado aquí") is None


# --- catálogo y relaciones sobre un corpus ficticio -------------------------


def _crudo(id_, ident, texto, fecha="2026", metadata=None):
    return {
        "id": id_,
        "fuente": "corte_suprema",
        "tipo": "sentencia",
        "identificador": ident,
        "titulo": f"Corte Suprema - Sentencia {ident}",
        "fecha": fecha,
        "texto": texto,
        "url_original": "https://consultaprovidencias.cortesuprema.gov.co/",
        "metadata": metadata if metadata is not None else {"sala": "Laboral", "magistrado": "Dr. Ficticio"},
    }


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    digital = [
        _crudo(
            "corte_suprema:laboral:SL99001-2026",
            "SL99001-2026",
            "SL99001-2026\nRadicación n.° 45678\nBogotá, diez (10) de marzo de dos mil veintiséis (2026)\n"
            "Como se dijo en CSJ SL99002-2026 y en SL99002-2026, y también en SL97777-2025, se reitera.",
        ),
        # registro antiguo: metadata como repr de dict (así quedó en los JSON crudos)
        _crudo(
            "corte_suprema:laboral:SL99002-2026",
            "SL99002-2026",
            "SL99002-2026\nRadicado n. 45678 \ntexto sin fecha completa (2026).",
            metadata="{'sala': 'Laboral', 'magistrado': 'Dra. Ficticia', 'ruta': '/x/SL99002-2026.docx'}",
        ),
    ]
    ocr = [
        _crudo(
            "corte_suprema:civil:SC99003-2026",
            "SC99003-2026",
            "SC99003－2026\nRadicación n.° 11001-02-03-000-2026-00001-00\nreitera SL99001－2026",
            metadata={"sala": "Civil", "paginas": 10, "paginas_ocr": 10, "confianza_ocr": 0.9612},
        )
    ]
    (tmp_path / "corte_suprema.json").write_text(json.dumps(digital), encoding="utf-8")
    (tmp_path / "corte_suprema_ocr.json").write_text(json.dumps(ocr), encoding="utf-8")
    cat, rel = tmp_path / "cat.json", tmp_path / "rel.db"
    # Otro test (test_prefijos_embedding) borra index.* de sys.modules: el
    # resolvedor puede estar usando un módulo distinto del que importó este
    # archivo. Se parchean los dos.
    import importlib

    vigente = importlib.import_module("index.providencias")
    for modulo in {id(m): m for m in (P, vigente)}.values():
        monkeypatch.setattr(modulo, "CATALOGO", cat)
        monkeypatch.setattr(modulo, "RELACIONES", rel)
        monkeypatch.setattr(modulo, "VERIFICACION", tmp_path / "verificacion.jsonl")
        monkeypatch.setattr(modulo, "_cat", None)
        monkeypatch.setattr(modulo, "leer_verificacion", lambda ruta=None: {})
    P.construir((tmp_path / "corte_suprema.json", tmp_path / "corte_suprema_ocr.json"), cat, rel)
    return tmp_path


def test_ficha_con_metadatos_y_precision_de_fecha(corpus):
    f = P.ficha("corte_suprema:laboral:SL99001-2026")
    assert f["corporacion"] == "Corte Suprema de Justicia"
    assert (f["sala"], f["tipo_providencia"], f["numerador"]) == ("Laboral", "sentencia", "SL99001-2026")
    assert (f["fecha"], f["fecha_precision"]) == ("2026-03-10", "dia")
    assert (f["radicado"], f["radicado_tipo"]) == ("45678", "interno")
    assert f["origen_texto"] == "digital" and f["confianza_ocr"] is None


def test_registro_antiguo_sin_fecha_completa_queda_en_el_anio(corpus):
    f = P.ficha("corte_suprema:laboral:SL99002-2026")
    assert (f["fecha"], f["fecha_precision"]) == ("2026", "anio")
    assert f["ponente"] == "Dra. Ficticia" and f["ruta_archivo"] == "/x/SL99002-2026.docx"


def test_texto_ocr_se_marca_y_normaliza_ancho_completo(corpus):
    f = P.ficha("corte_suprema:civil:SC99003-2026")
    assert f["origen_texto"] == "ocr" and f["confianza_ocr"] == 0.961
    assert f["radicado_tipo"] == "cui"
    rel = P.relaciones("corte_suprema:civil:SC99003-2026")
    assert [c["identificador"] for c in rel["cita_a"]] == ["SL99001-2026"]  # "SL99001－2026" del OCR


def test_relaciones_confirmadas_no_resueltas_y_sin_autocita(corpus):
    rel = P.relaciones("corte_suprema:laboral:SL99001-2026")
    por_id = {c["identificador"]: c for c in rel["cita_a"]}
    assert set(por_id) == {"SL99002-2026", "SL97777-2025"}  # no se cita a sí misma
    assert por_id["SL99002-2026"]["estado"] == "confirmada" and por_id["SL99002-2026"]["veces"] == 2
    assert por_id["SL97777-2025"]["estado"] == "no_resuelta" and not por_id["SL97777-2025"]["en_indice"]
    assert "CSJ SL99002-2026" in por_id["SL99002-2026"]["contexto"]
    citada = P.relaciones("corte_suprema:laboral:SL99001-2026")["citada_por"]
    assert [c["documento_id"] for c in citada] == ["corte_suprema:civil:SC99003-2026"]


def test_enlaces_sin_verificar_no_se_presentan_como_ficha(corpus):
    e = P.ficha("corte_suprema:laboral:SL99001-2026")["enlaces"]
    assert e["ficha"] is None and e["archivo"] is None and e["estado"] == "no_verificado"
    assert e["buscar_en_ojeador"] == "https://ojeador.cortesuprema.gov.co/resultados?q=SL99001-2026"
    assert e["buscador_general"].startswith("https://consultaprovidencias")


def test_enlace_verificado_lleva_el_hash_y_el_ambiguo_no(corpus, monkeypatch):
    P.catalogo()  # carga el catálogo antes de fijar la verificación
    monkeypatch.setattr(
        P,
        "_verif",
        {
            "SL99001-2026": {
                "canonica": "SL99001-2026",
                "estado": "verificada",
                "numerador": "SL99001-2026",
                "hash": "abc123",
                "ubicacion": "SALAS/LABORAL/2026/X/SL99001-2026.docx",
                "fecha": "2026-03-11",
                "consultado": "2026-04-01T10:00:00",
            },
            "SL99002-2026": {"canonica": "SL99002-2026", "estado": "ambigua", "consultado": "2026-04-01"},
        },
    )
    f = P.ficha("corte_suprema:laboral:SL99001-2026")
    assert f["enlaces"]["ficha"] == "https://ojeador.cortesuprema.gov.co/caso/SL99001-2026?doc=abc123"
    assert f["enlaces"]["archivo"].endswith("SALAS/LABORAL/2026/X/SL99001-2026.docx")
    assert f["fecha_origen"] == "Ojeador (Corte Suprema)" and f["fecha"] == "2026-03-11"
    amb = P.ficha("corte_suprema:laboral:SL99002-2026")["enlaces"]
    assert amb["ficha"] is None and amb["estado"] == "ambigua"


def test_anotar_solo_toca_la_suprema_y_sin_catalogo_no_hace_nada(corpus, monkeypatch):
    res = [
        {"id": "corte_suprema:laboral:SL99001-2026::frag0", "fuente": "corte_suprema"},
        {"id": "legalize_co_github:LEY-1480-2011::frag3", "fuente": "legalize_co_github"},
    ]
    a = P.anotar(res)
    assert a[0]["ficha"]["numerador"] == "SL99001-2026" and "ficha" not in a[1]
    monkeypatch.setattr(P, "_cat", {})
    assert P.anotar(res) == res


# --- resolución de citas --------------------------------------------------


class _Col:
    def get(self, where, include, limit):
        d = where["documento_id"]
        return {"ids": [f"{d}::frag0"], "documents": [f"texto de {d}"], "metadatas": [{"orden": 0}]}


@pytest.fixture()
def sin_vigencia(monkeypatch):
    monkeypatch.setattr("index.vigencia.anotar", lambda r: r)


def test_resuelve_identificador_exacto(corpus, sin_vigencia):
    r = rc.resolver("qué dijo la CSJ SL99001-2026", _Col())
    assert r.cita.sentencia == "SL99001-2026"
    assert [f["id"] for f in r.resultados] == ["corte_suprema:laboral:SL99001-2026::frag0"]
    assert r.resultados[0]["cita_exacta"] and r.resultados[0]["ficha"]["numerador"] == "SL99001-2026"


def test_no_esta_en_el_indice_no_es_no_existe(corpus, sin_vigencia):
    r = rc.resolver("SL97777-2025", _Col())
    assert (
        r.resultados == []
        and "no está en el índice" in r.aviso
        and "no quiere decir que no exista" in r.aviso
    )


def test_referencia_sin_anio_unica_y_sin_candidatos(corpus, sin_vigencia):
    r = rc.resolver("la SL99001", _Col())
    assert r.resultados and "no trae año" in r.aviso
    assert rc.resolver("la SL94444", _Col()).resultados == []


def test_radicado_identifica_el_proceso_no_la_decision(corpus, sin_vigencia):
    r = rc.resolver("radicado 45678", _Col())
    assert r.cita.tipo == "radicado" and len(r.resultados) == 2
    assert "identifica el proceso" in r.aviso


def test_radicado_del_consejo_de_estado_no_se_resuelve_con_la_suprema(corpus, sin_vigencia):
    assert rc._resolver_suprema("11001-03-15-000-2020-01234-00", _Col(), 5) is None


def test_sin_referencias_de_la_suprema_sigue_la_resolucion_de_normas(corpus, sin_vigencia):
    assert rc._resolver_suprema("art. 64 del CST", _Col(), 5) is None
    assert rc._resolver_suprema("T-760/08", _Col(), 5) is None


# --- citas antiguas: sala + fecha + radicado ----------------------------------


@pytest.mark.parametrize(
    "texto, sala, fecha, radicado",
    [
        ("CSJ SL, 5 ago. 2014, rad. 45678", "Laboral", "2014-08-05", "45678"),
        ("(CSJ SL 10 mar. 2026, rad. 45678)", "Laboral", "2026-03-10", "45678"),
        (
            "Sala de Casación Laboral, sentencia del 5 de agosto de 2014, radicación 45678",
            "Laboral",
            "2014-08-05",
            "45678",
        ),
        ("CSJ SCC, 12 de diciembre de 2005, rad. n.° 1999-00123", "Civil", "2005-12-12", None),
        ("Corte Suprema de Justicia, sentencia de 1 de febrero de 2011", None, "2011-02-01", None),
        ("rad. 45678 del 5 de agosto de 2014", None, "2014-08-05", "45678"),
        ("CSJ SP, 3 sept. 2008, rad. 29.000", "Penal", "2008-09-03", None),
        (
            "Corte Suprema, Sala de Casación Civil. Sentencia de 7 de mayo de 1998",
            "Civil",
            "1998-05-07",
            None,
        ),
    ],
)
def test_reconoce_citas_antiguas(texto, sala, fecha, radicado):
    r = P.parsear_antigua(texto)
    assert r is not None and (r.sala, r.fecha) == (sala, fecha)
    if radicado:
        assert r.radicado == radicado


@pytest.mark.parametrize(
    "texto",
    [
        "el 5 de agosto de 2014 me despidieron sin justa causa",  # fecha suelta: prosa
        "Consejo de Estado, Sección Tercera, sentencia del 5 de agosto de 2014, rad. 45678",
        "Corte Constitucional, sentencia del 5 de agosto de 2014",
        "CSJ SL, 31 feb. 2014, rad. 45678",  # fecha imposible
        "CSJ SL131-2026 del 11 de febrero de 2026",  # el identificador nuevo ya la resuelve
        "la Corte Suprema dijo algo. Luego, el 5 de agosto de 2014, renuncié",  # otra oración
        # visto en el corpus: la fecha es del fallo del tribunal, no una cita
        "Mediante sentencia CSJ SL1671-2023, esta Sala CASÓ la proferida el 30 de septiembre de 2022",
    ],
)
def test_no_inventa_citas_antiguas(texto):
    assert P.referencias_antiguas(texto) == []


def test_el_encabezado_de_pagina_no_es_el_radicado_de_la_cita():
    r = P.parsear_antigua(
        "Corte Suprema, sentencia del 25 de enero 2017». SCLAPT-10 V.00 10 Radicación n.° 79767"
    )
    assert r is not None and r.radicado is None


def test_numero_sin_anio_toma_el_anio_de_la_fecha():
    # vistos en el corpus (23-nov-2026)
    r = P.parsear_antigua("(CSJ SC1171, rad. 2012-00715-01, 8 abr. 2022)")
    assert (r.identificador, r.sala, r.fecha) == ("SC1171-2022", "Civil", "2022-04-08")
    assert P.parsear_antigua("CSJ, SC 2407 de 21 de julio de 2020").identificador == "SC2407-2020"


def test_numero_que_no_esta_no_se_cambia_por_otra_de_la_misma_fecha(corpus, sin_vigencia):
    # SL99001-2026 es del 10 de marzo de 2026; la cita nombra otra (SL99009)
    r = rc.resolver("CSJ SL99009, 10 mar. 2026", _Col())
    assert r.resultados == [] and "no quiere decir que no exista" in r.aviso
    ok = rc.resolver("CSJ SL99001, 10 mar. 2026", _Col())
    assert [f["id"] for f in ok.resultados] == [
        "corte_suprema:laboral:SL99001-2026::frag0"
    ] and ok.aviso == ""


def test_cita_antigua_exacta_se_resuelve_y_confirma_relacion(corpus, sin_vigencia):
    r = rc.resolver("qué dijo la CSJ SL, 10 mar. 2026, rad. 45678", _Col())
    assert [f["id"] for f in r.resultados] == ["corte_suprema:laboral:SL99001-2026::frag0"]
    assert r.aviso == "" and r.cita.sentencia == "CSJ Laboral, 2026-03-10, rad. 45678"


def test_cita_antigua_con_fecha_solo_de_anio_avisa(corpus, sin_vigencia):
    # SL99002-2026 tiene el radicado 45678 pero el índice solo sabe el año
    r = rc.resolver("CSJ SL, 4 may. 2026, rad. 45678", _Col())
    assert [f["id"] for f in r.resultados] == ["corte_suprema:laboral:SL99002-2026::frag0"]
    assert "no tiene la fecha completa" in r.aviso


def test_cita_antigua_sin_radicado_y_sin_coincidencias(corpus, sin_vigencia):
    r = rc.resolver("Corte Suprema, sentencia del 10 de marzo de 2026", _Col())
    assert len(r.resultados) == 1 and "puede haber otras" in r.aviso
    nada = rc.resolver("CSJ SL, 9 ene. 2001, rad. 11111", _Col())
    assert nada.resultados == [] and "no quiere decir que no exista" in nada.aviso


def test_relacion_por_cita_antigua(tmp_path, monkeypatch):
    citada = _crudo(
        "corte_suprema:laboral:SL99010-2016",
        "SL99010-2016",
        "SL99010-2016\nRadicación n.° 41000\n"
        "Bogotá, cinco (5) de agosto de dos mil dieciséis (2016)\nresuelve",
        fecha="2016",
    )
    citante = _crudo(
        "corte_suprema:laboral:SL99011-2020",
        "SL99011-2020",
        "SL99011-2020\nComo lo ha dicho la Sala (CSJ SL, 5 ago. 2016, rad. 41000) y también "
        "CSJ SL, 6 ago. 2016, rad. 42000, se reitera. La Corte Suprema NO CASA la sentencia "
        "proferida el 5 de agosto de 2016.",  # solo fecha: no crea relación
        fecha="2020",
    )
    ruta = tmp_path / "cs.json"
    ruta.write_text(json.dumps([citada, citante]), encoding="utf-8")
    cat, rel = tmp_path / "cat.json", tmp_path / "rel.db"
    monkeypatch.setattr(P, "RELACIONES", rel)
    monkeypatch.setattr(P, "CATALOGO", cat)
    monkeypatch.setattr(P, "_cat", None)
    monkeypatch.setattr(P, "leer_verificacion", lambda ruta=None: {})
    datos = P.construir((ruta,), cat, rel)
    assert datos["relaciones"]["confirmadas"] == 1 and datos["relaciones"]["no_resueltas"] == 1
    sal = {c["identificador"]: c for c in P.relaciones("corte_suprema:laboral:SL99011-2020")["cita_a"]}
    assert sal["CSJ Laboral, 2016-08-05, rad. 41000"]["documento_id"] == "corte_suprema:laboral:SL99010-2016"
    assert sal["CSJ Laboral, 2016-08-06, rad. 42000"]["estado"] == "no_resuelta"
    entra = P.relaciones("corte_suprema:laboral:SL99010-2016")["citada_por"]
    assert [c["documento_id"] for c in entra] == ["corte_suprema:laboral:SL99011-2020"]
