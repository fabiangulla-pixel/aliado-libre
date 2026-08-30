from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_crawl_no_repite_documentos_previos():
    from ingest.schema import Documento

    previo = Documento(
        id="dian:tributario:oficio_dian_18075_2023",
        fuente="dian",
        tipo="concepto",
        identificador="oficio_dian_18075_2023",
        titulo="Concepto ya descargado",
        fecha=None,
        texto="texto previo",
        url_original="https://x",
        metadata={"materia": "tributario"},
    )

    def listar_partes_falso(sesion, pagina_opcion):
        # solo la primera opción de tributario trae el documento ya visto;
        # el resto de opciones/materias no traen nada (para aislar el caso)
        if pagina_opcion == "t_1_normativa_tributaria":
            return ["docs/oficio_dian_18075_2023.htm"]
        return []

    with (
        patch("ingest.fuentes.dian._listar_partes", side_effect=listar_partes_falso),
        patch("ingest.fuentes.dian._extraer_documento") as mock_extraer,
    ):
        docs = dian.crawl(max_documentos=100, pausa_segundos=0, documentos_previos=[previo])

    assert docs == [previo]
    mock_extraer.assert_not_called()
