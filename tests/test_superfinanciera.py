from pathlib import Path
from unittest.mock import MagicMock, patch

from ingest.fuentes import superfinanciera as sf

FIXTURES = Path(__file__).parent / "fixtures"


def _bloques_fixture() -> list[str]:
    html = (FIXTURES / "superfinanciera_respuesta.html").read_bytes().decode("iso-8859-1")
    return html.split('<div id="registro">')[1:]


def test_texto_campo_extrae_algun_campo_de_cada_registro():
    # No todos los registros tienen "Título de la norma" (algunos son solo
    # "Concepto"), pero todos deben tener al menos uno de los dos campos.
    for bloque in _bloques_fixture():
        titulo = sf._texto_campo(bloque, "T&iacute;tulo de la norma")
        concepto = sf._texto_campo(bloque, "Concepto")
        assert titulo or concepto


def test_a_documento_sin_descarga_usa_resumen():
    bloque = _bloques_fixture()[0]
    with patch("ingest.fuentes.superfinanciera._descargar_archivo_texto", return_value=None):
        doc = sf._a_documento(MagicMock(), bloque, 1)
    assert doc is not None
    assert doc.fuente == "superfinanciera"
    assert doc.tipo == "concepto"
    assert len(doc.texto) > 0


def test_a_documento_prefiere_texto_completo_si_es_mas_largo():
    bloque = _bloques_fixture()[0]
    texto_largo = "Texto completo del concepto. " * 20
    with patch("ingest.fuentes.superfinanciera._descargar_archivo_texto", return_value=texto_largo):
        doc = sf._a_documento(MagicMock(), bloque, 1)
    assert doc.texto == texto_largo


def test_a_documento_none_si_bloque_vacio():
    doc = sf._a_documento(MagicMock(), "<div>nada relevante aquí</div>", 1)
    assert doc is None
