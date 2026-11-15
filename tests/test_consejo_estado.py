from pathlib import Path
from unittest.mock import patch

from ingest.fuentes import consejo_estado as ce
from ingest.schema import Documento

FIXTURE = Path(__file__).parent / "fixtures" / "consejo_estado_2025315.html"


def _crudo() -> str:
    return FIXTURE.read_bytes().decode("cp1252")


def test_a_documento_extrae_encabezado_de_la_providencia():
    doc = ce.a_documento(2025315, _crudo())
    assert doc is not None
    assert doc.id == "consejo_estado:2025315"
    assert doc.fecha == "2006"
    assert doc.identificador.startswith("25000-23-26-000-1998-05909-01")
    assert (
        doc.metadata["seccion"].upper().startswith("SECCI") and "TERCERA" in doc.metadata["seccion"].upper()
    )
    assert "RAMIRO SAAVEDRA BECERRA" in doc.metadata["ponente"]
    assert "Sección Tercera" in doc.titulo or "Secci" in doc.titulo


def test_a_documento_limpia_html_y_conserva_acentos():
    doc = ce.a_documento(2025315, _crudo())
    assert "<" not in doc.texto and "&oacute;" not in doc.texto
    assert "IMPEDIMENTO" in doc.texto
    assert "Bogotá" in doc.texto
    assert "�" not in doc.texto


def test_a_documento_descarta_vacios_y_ajenos():
    assert ce.a_documento(1, "") is None
    assert ce.a_documento(1, "<p>" + "texto cualquiera " * 100 + "</p>") is None


def test_numeros_respeta_rangos_y_reanuda():
    assert ce.numeros(((10, 13), (20, 22))) == [10, 11, 12, 20, 21]
    assert ce.numeros(((10, 13), (20, 22)), desde=12) == [12, 20, 21]


def test_crawl_salta_previos_y_marca_avance_por_lote():
    previo = Documento(
        id="consejo_estado:11",
        fuente="consejo_estado",
        tipo="sentencia",
        identificador="x",
        titulo="t",
        fecha=None,
        texto="previo",
        url_original="",
        metadata={},
    )
    pedidos, avances = [], []

    def falso_descargar(sesion, nr):
        pedidos.append(nr)
        return _crudo() if nr != 12 else None

    with patch.object(ce, "_descargar", side_effect=falso_descargar), patch.object(ce.time, "sleep"):
        docs = ce.crawl(
            max_documentos=100,
            documentos_previos=[previo],
            rangos=((10, 14),),
            al_avanzar=avances.append,
            hilos=1,
            lote=2,
        )
    assert sorted(pedidos) == [10, 12, 13]
    assert [d.id for d in docs] == ["consejo_estado:11", "consejo_estado:10", "consejo_estado:13"]
    assert avances == [11, 13]
