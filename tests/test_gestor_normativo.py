from pathlib import Path
from unittest.mock import patch

from ingest.fuentes.gestor_normativo import _fix_mojibake, _parsear_documento, crawl
from ingest.schema import Documento

FIXTURE = Path(__file__).parent / "fixtures" / "gestor_normativo_decreto1083.html"


def _html_fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_fix_mojibake_revierte_doble_codificacion():
    assert _fix_mojibake("producciÃ³n") == "producción"


def test_fix_mojibake_no_rompe_texto_ya_correcto():
    # Si el texto no está doblemente codificado, latin1->utf8 puede fallar
    # (UnicodeDecodeError) y debe devolverse tal cual, no reventar.
    assert _fix_mojibake("producción normal") == "producción normal"


def test_fix_mojibake_corrige_palabras_sueltas_en_texto_mixto():
    # Caso real observado en producción: una línea larga con la MAYORÍA de
    # palabras doblemente codificadas y alguna ya correcta (o viceversa) no
    # debe perder la corrección de las demás solo porque una falla el re-decode
    # de la línea completa.
    texto = "La producciÃ³n normativa y también la protección de datos."
    corregido = _fix_mojibake(texto)
    assert "producción normativa" in corregido
    assert "protección de datos" in corregido


def test_parsear_documento_extrae_texto_completo():
    doc = _parsear_documento(_html_fixture(), "62866", "https://example.test/norma.php?i=62866")
    assert doc is not None
    assert doc.fuente == "gestor_normativo"
    assert doc.tipo == "decreto"
    assert "Decreto 1083 de 2015" in doc.titulo
    assert len(doc.texto) > 500_000  # es un decreto único reglamentario, muy largo
    assert "producción" in doc.texto  # confirma que el mojibake se corrigió


def test_parsear_documento_extrae_vigencias():
    doc = _parsear_documento(_html_fixture(), "62866", "https://example.test/norma.php?i=62866")
    vigencias = doc.metadata["vigencias"]
    assert len(vigencias) > 50  # el decreto tiene un historial de modificaciones extenso
    tipos_esperados = {"Modificado por", "Adicionado por", "Deroga", "Reglamenta parcialmente"}
    tipos_encontrados = {v["tipo"] for v in vigencias}
    assert tipos_esperados & tipos_encontrados  # al menos algunos tipos conocidos aparecen
    for v in vigencias:
        assert v["id_relacionado"].isdigit()


def test_parsear_documento_devuelve_none_si_falta_contenido():
    html_vacio = "<html><head><title>Norma vacía</title></head><body>nada aquí</body></html>"
    doc = _parsear_documento(html_vacio, "1", "https://example.test/norma.php?i=1")
    assert doc is None


def _doc_previo(norma_id: str, vigencias: list[dict] | None = None) -> Documento:
    return Documento(
        id=f"gestor_normativo:{norma_id}",
        fuente="gestor_normativo",
        tipo="decreto",
        identificador=f"Decreto {norma_id}",
        titulo=f"Decreto {norma_id}",
        fecha=None,
        texto="texto ya conocido de una corrida anterior",
        url_original=f"https://example.test/norma.php?i={norma_id}",
        metadata={"vigencias": vigencias or []},
    )


def test_crawl_no_vuelve_a_descargar_documentos_previos():
    previos = [_doc_previo("100"), _doc_previo("200")]
    with (
        patch("ingest.fuentes.gestor_normativo._sesion"),
        patch("ingest.fuentes.gestor_normativo.obtener_norma") as mock_obtener,
    ):
        resultado = crawl(["100"], max_documentos=2, pausa_segundos=0, documentos_previos=previos)

    mock_obtener.assert_not_called()
    assert len(resultado) == 2
    assert {d.id for d in resultado} == {"gestor_normativo:100", "gestor_normativo:200"}


def test_crawl_expande_desde_vigencias_de_documentos_previos():
    previos = [
        _doc_previo("100", vigencias=[{"tipo": "Modifica", "id_relacionado": "300", "descripcion": ""}])
    ]
    nuevo = _doc_previo("300")

    with (
        patch("ingest.fuentes.gestor_normativo._sesion"),
        patch("ingest.fuentes.gestor_normativo.obtener_norma", return_value=nuevo) as mock_obtener,
    ):
        resultado = crawl(["100"], max_documentos=2, pausa_segundos=0, documentos_previos=previos)

    # "100" no se refetch (ya estaba); "300" sí, porque salió de sus vigencias
    mock_obtener.assert_called_once()
    assert mock_obtener.call_args[0][1] == "300"
    assert {d.id for d in resultado} == {"gestor_normativo:100", "gestor_normativo:300"}
