from pathlib import Path
from unittest.mock import MagicMock

from ingest.fuentes import dian

FIXTURES = Path(__file__).parent / "fixtures"


def _sesion_con_respuesta(bytes_respuesta: bytes, status: int = 200) -> MagicMock:
    sesion = MagicMock()
    respuesta = MagicMock(status_code=status, content=bytes_respuesta)
    sesion.get.return_value = respuesta
    return sesion


def test_listar_partes_extrae_rutas_docs():
    html_bytes = (FIXTURES / "dian_parte.html").read_bytes()
    sesion = _sesion_con_respuesta(html_bytes)
    # la segunda llamada (parte_02) debe fallar (404) para detener la paginación
    sesion.get.side_effect = [
        MagicMock(status_code=200, text=html_bytes.decode("latin1")),
        MagicMock(status_code=404),
    ]
    rutas = dian._listar_partes(sesion, "t_2_doctrina_tributaria")
    assert all(r.startswith("docs/") for r in rutas)
    assert len(rutas) > 0


def test_extraer_documento_parsea_texto_y_fecha():
    html_bytes = (FIXTURES / "dian_documento.htm").read_bytes()
    sesion = _sesion_con_respuesta(html_bytes)
    doc = dian._extraer_documento(sesion, "tributario", "concepto", "docs/oficio_dian_18075_2023.htm")
    assert doc is not None
    assert doc.fuente == "dian"
    assert doc.tipo == "concepto"
    assert len(doc.texto) > 80
    assert "dian:tributario:" in doc.id


def test_extraer_documento_none_si_404():
    sesion = _sesion_con_respuesta(b"", status=404)
    doc = dian._extraer_documento(sesion, "tributario", "concepto", "docs/no_existe.htm")
    assert doc is None
