from ingest.normalizar import fecha_es_a_iso, fix_mojibake


def test_fecha_es_a_iso_convierte_formato_estandar():
    assert fecha_es_a_iso("26 de mayo de 2015") == "2015-05-26"


def test_fecha_es_a_iso_dia_de_un_digito():
    assert fecha_es_a_iso("5 de agosto de 2015") == "2015-08-05"


def test_fecha_es_a_iso_devuelve_original_si_no_matchea():
    assert fecha_es_a_iso("formato desconocido") == "formato desconocido"


def test_fecha_es_a_iso_none_pasa_igual():
    assert fecha_es_a_iso(None) is None


def test_fix_mojibake_revierte_doble_codificacion():
    assert fix_mojibake("producciÃ³n") == "producción"


def test_fix_mojibake_no_rompe_texto_ya_correcto():
    assert fix_mojibake("producción normal") == "producción normal"
