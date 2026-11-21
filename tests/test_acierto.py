from finetune.eval.acierto import es_equivalente, es_exacto, norma, posicion


def test_norma_reconoce_ids_y_titulos():
    assert norma("LEY-1480-2011") == ("ley", 1480, "2011")
    assert norma("ley_1480_2011".replace("_", "-")) == ("ley", 1480, "2011")
    assert norma("Ley 142 de 1994 - Gestor Normativo") == ("ley", 142, "1994")
    assert norma("Decreto 2663 de 1950") == ("dec", 2663, "1950")
    assert norma("Sentencia T-123 de 2020") is None
    assert norma(None, "") is None


def test_misma_ley_en_otra_fuente_es_equivalente_no_exacta():
    caso = {"documento_id": "dian:aduanero:ley_1480_2011"}
    r = {"documento_id": "legalize_co_github:LEY-1480-2011"}
    assert not es_exacto(r, caso)
    assert es_equivalente(r, caso)


def test_norma_esperada_del_caso_cuenta():
    caso = {
        "documento_id": "dian:tributario:oficio_dian_906224_2022",
        "norma_esperada": "Ley 1480 de 2011, articulo 51",
    }
    assert es_equivalente({"documento_id": "legalize_co_github:LEY-1480-2011"}, caso)
    assert not es_equivalente({"documento_id": "legalize_co_github:LEY-1481-2011"}, caso)


def test_titulo_del_gestor_normativo():
    caso = {"documento_id": "legalize_co_github:LEY-142-1994"}
    r = {"documento_id": "gestor_normativo:2752", "titulo_documento": "Ley 142 de 1994 - Gestor Normativo"}
    assert es_equivalente(r, caso)


def test_sentencia_solo_vale_exacta():
    caso = {"documento_id": "corte_constitucional:23601"}
    assert not es_equivalente({"documento_id": "corte_constitucional:99999"}, caso)
    assert es_equivalente({"documento_id": "corte_constitucional:23601"}, caso)


def test_posicion():
    caso = {"documento_id": "dian:aduanero:ley_1480_2011"}
    res = [{"documento_id": "sic:x"}, {"documento_id": "legalize_co_github:LEY-1480-2011"}]
    assert posicion(res, caso) is None
    assert posicion(res, caso, equivalente=True) == 1


def test_codigos_por_nombre():
    caso = {"documento_id": "superfinanciera:1571", "norma_esperada": "Código de Comercio, artículo 1058"}
    assert es_equivalente({"documento_id": "legalize_co_github:DECRETO-410-1971"}, caso)
    assert norma("Código de Procedimiento Penal") == ("ley", 906, "2004")
    assert norma("Código Penal, artículo 2") == ("ley", 599, "2000")
    assert norma("Ley 1437 de 2011 (CPACA)") == ("ley", 1437, "2011")
    assert norma("Jurisprudencia de la Corte Constitucional") is None


def test_vale_la_norma_de_la_referencia_aunque_el_ancla_sea_otra():
    caso = {
        "documento_id": "legalize_co_github:LEY-33-1986",
        "norma_esperada": "Ley 769 de 2002 (Código vigente). El índice tiene la Ley 33 de 1986",
    }
    assert es_equivalente({"documento_id": "legalize_co_github:LEY-769-2002"}, caso)
    assert es_equivalente({"documento_id": "legalize_co_github:LEY-33-1986"}, caso)
    assert not es_equivalente({"documento_id": "legalize_co_github:LEY-1383-2010"}, caso)


def test_aceptables_revisados_por_una_persona():
    caso = {"documento_id": "supersociedades:A", "aceptables": ["supersociedades:B"]}
    assert es_equivalente({"documento_id": "supersociedades:B"}, caso)
    assert not es_exacto({"documento_id": "supersociedades:B"}, caso)
    assert not es_equivalente({"documento_id": "supersociedades:C"}, caso)
