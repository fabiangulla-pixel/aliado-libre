"""Ingester de los normogramas de Superservicios y Supersalud, y texto completo de la Corte."""

from unittest.mock import MagicMock

from ingest.fuentes import superservicios as S
from ingest.schema import Documento

DOC_HTML = """<html><head><title>X</title></head><body>
<div class="titulo-documento">Concepto 1 de 2010 SSPD</div>
<div class="panel-documento"><p>CONCEPTO 1 DE 2010</p><p>Fecha: 04-01-2010</p>
<p>La empresa no puede suspender el servicio sin aviso previo al usuario.</p>
<p>{relleno}</p></div></body></html>""".format(relleno="texto " * 40)


def _sesion(*respuestas):
    sesion = MagicMock()
    sesion.get.side_effect = list(respuestas)
    return sesion


def test_listar_anio_extrae_rutas_unicas_de_cualquier_entidad():
    html = (
        '<a href="docs/concepto_superservicios_0000001_2010.htm">1</a>'
        '<a href="docs/concepto_superservicios_0000001_2010.htm">1</a>'
        '<a href="docs/concepto_supersalud_0254801_2023.htm">2</a>'
        '<a href="docs/resolucion_x_1_2010.htm">no</a>'
    )
    rutas = S.listar_anio(_sesion(MagicMock(status_code=200, text=html)), 2010)
    assert rutas == [
        "docs/concepto_supersalud_0254801_2023.htm",
        "docs/concepto_superservicios_0000001_2010.htm",
    ]


def test_listar_anio_vacio_si_no_existe_la_pagina():
    assert S.listar_anio(_sesion(MagicMock(status_code=404, text="")), 1990) == []


def test_extraer_parsea_titulo_fecha_numerica_y_fuente():
    sesion = _sesion(MagicMock(status_code=200, content=DOC_HTML.encode("utf-8")))
    doc = S.extraer(sesion, "docs/concepto_superservicios_0000001_2010.htm")
    assert doc.id == "superservicios:concepto_superservicios_0000001_2010"
    assert doc.titulo == "Concepto 1 de 2010 SSPD"
    assert doc.fecha == "2010-01-04"
    assert "suspender el servicio" in doc.texto


def test_extraer_con_otra_fuente_y_base():
    sesion = _sesion(MagicMock(status_code=200, content=DOC_HTML.encode("utf-8")))
    doc = S.extraer(sesion, "docs/concepto_supersalud_0254801_2023.htm", "https://b/", "supersalud")
    assert doc.id == "supersalud:concepto_supersalud_0254801_2023"
    assert doc.fuente == "supersalud"
    assert doc.url_original == "https://b/docs/concepto_supersalud_0254801_2023.htm"


def test_crawl_no_repite_lo_ya_descargado():
    previo = Documento(
        id="superservicios:concepto_superservicios_0000001_2010",
        fuente="superservicios",
        tipo="concepto",
        identificador="concepto_superservicios_0000001_2010",
        titulo="ya",
        fecha=None,
        texto="ya",
        url_original="x",
        metadata={},
    )
    import ingest.fuentes.superservicios as modulo

    listado = '<a href="docs/concepto_superservicios_0000001_2010.htm"></a>'
    sesion = MagicMock()
    sesion.get.side_effect = [MagicMock(status_code=200, text=listado)]
    original = modulo.requests.Session
    modulo.requests.Session = lambda: sesion
    try:
        docs = S.crawl([2010], pausa_segundos=0, documentos_previos=[previo])
    finally:
        modulo.requests.Session = original
    assert docs == [previo]
    assert sesion.get.call_count == 1  # solo el listado, ningún documento


def test_corte_texto_completo_une_lineas_y_conserva_parrafos():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from completar_corte_texto_completo import sin_sintesis, texto_de_html

    html = "<html><body><p>La igualdad\nconstituye fundamento</p><p>Segundo p\xe1rrafo</p></body></html>"
    texto = texto_de_html(html.encode("windows-1252"))
    assert "La igualdad constituye fundamento" in texto
    assert "Segundo párrafo" in texto
    assert sin_sintesis({"_source": {"prov_sintesis": "Sin información"}})
    assert not sin_sintesis({"_source": {"prov_sintesis": "Algo"}})
