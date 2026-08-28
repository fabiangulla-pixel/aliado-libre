from pathlib import Path

from ingest.fuentes.gestor_normativo import _fix_mojibake, _parsear_documento

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
