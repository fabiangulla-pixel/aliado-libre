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


def test_extraer_texto_binario_docx():
    contenido = (FIXTURES / "superfinanciera_concepto.docx").read_bytes()
    texto = sf._extraer_texto_binario(contenido)
    assert texto is not None
    assert "Concepto de prueba" in texto
    assert "Segundo párrafo" in texto


def test_extraer_texto_binario_no_confunde_docx_con_texto_plano():
    # bug real de una corrida anterior: decodificar el .docx (zip binario)
    # como texto producía basura ~30x más pesada que el contenido real
    contenido = (FIXTURES / "superfinanciera_concepto.docx").read_bytes()
    texto = sf._extraer_texto_binario(contenido)
    assert len(texto) < len(contenido)


def test_extraer_texto_binario_none_si_docx_corrupto():
    assert sf._extraer_texto_binario(b"PK\x03\x04basura_no_es_un_zip_valido") is None


def test_extraer_texto_binario_none_si_es_audio_mp3():
    # bug real: algunos "archivos de texto" del catálogo son en realidad
    # grabaciones .mp3 de audiencias/fallos — decodificarlas como latin1
    # (que nunca falla) producía decenas de MB de basura por documento
    encabezado_mp3 = b"ID3\x03\x00\x00\x00\x00\x1fvGEOB\x00\x00\x00x\x00\x00" + bytes(range(256)) * 50
    assert sf._extraer_texto_binario(encabezado_mp3) is None


def test_parece_texto_true_para_texto_real():
    assert sf._parece_texto("Concepto jurídico con tildes y ñ, todo normal.".encode())


def test_parece_texto_false_para_binario():
    assert not sf._parece_texto(bytes(range(256)) * 10)


def test_a_documento_none_si_bloque_vacio():
    doc = sf._a_documento(MagicMock(), "<div>nada relevante aquí</div>", 1)
    assert doc is None


def test_crawl_reanuda_desde_el_indice_global_previo():
    from ingest.schema import Documento

    previos = [
        Documento(
            id="superfinanciera:37:algo",
            fuente="superfinanciera",
            tipo="concepto",
            identificador="algo",
            titulo="algo",
            fecha=None,
            texto="texto previo",
            url_original="https://x",
        )
    ]
    with patch("ingest.fuentes.superfinanciera._obtener_pagina", return_value="<html></html>") as mock_pagina:
        docs = sf.crawl(max_documentos=2, documentos_previos=previos)
    assert docs == previos  # sin bloques nuevos, no agrega nada más
    llamada_desde = mock_pagina.call_args[0][1]
    assert llamada_desde == 38  # 37 + 1, no reempieza en 1
