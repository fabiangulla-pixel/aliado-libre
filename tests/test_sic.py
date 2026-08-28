import json
from pathlib import Path
from unittest.mock import patch

from ingest.fuentes.sic import _a_documento

FIXTURE = Path(__file__).parent / "fixtures" / "sic_respuesta_es.json"


def _hit_fixture() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["hits"]["hits"][0]


def test_a_documento_construye_documento_con_texto_descargado():
    texto = "Texto extraído del PDF real. " * 10  # supera el mínimo de 100 caracteres
    with patch("ingest.fuentes.sic._descargar_texto_pdf", return_value=texto):
        doc = _a_documento(None, _hit_fixture())

    assert doc is not None
    assert doc.fuente == "sic"
    assert doc.tipo == "sentencia"
    assert doc.texto == texto


def test_a_documento_none_si_no_hay_ruta_s3():
    hit_sin_ruta = {"_id": "1", "_source": {"informacion": {}, "documento_resumen": {}}}
    doc = _a_documento(None, hit_sin_ruta)
    assert doc is None


def test_a_documento_none_si_descarga_falla():
    with patch("ingest.fuentes.sic._descargar_texto_pdf", return_value=None):
        doc = _a_documento(None, _hit_fixture())
    assert doc is None


def test_a_documento_none_si_texto_muy_corto():
    with patch("ingest.fuentes.sic._descargar_texto_pdf", return_value="corto"):
        doc = _a_documento(None, _hit_fixture())
    assert doc is None


def test_a_documento_extrae_tesauro():
    with patch("ingest.fuentes.sic._descargar_texto_pdf", return_value="Texto suficientemente largo " * 5):
        doc = _a_documento(None, _hit_fixture())
    assert isinstance(doc.metadata["tesauro"], list)
