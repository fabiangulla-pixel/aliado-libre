from index.normas import norma, norma_de_resultado


def test_el_id_manda():
    assert norma_de_resultado({"documento_id": "legalize_co_github:LEY-1480-2011"}) == ("ley", 1480, "2011")
    assert norma_de_resultado({"documento_id": "dian:aduanero:decreto_1074_2015"}) == ("dec", 1074, "2015")


def test_titulo_que_empieza_por_la_norma_cuenta():
    r = {"documento_id": "gestor_normativo:2752", "titulo_documento": "Ley 142 de 1994 - Gestor Normativo"}
    assert norma_de_resultado(r) == ("ley", 142, "1994")


def test_documento_que_solo_menciona_la_norma_no_es_la_norma():
    """Un oficio sobre la Ley 1480 no es la Ley 1480: si contara, la métrica
    premiaría traer cualquier concepto que la cite y el enrutador lo subiría al
    puesto 1 creyendo que es la ley."""
    r = {
        "documento_id": "dian:tributario:oficio_dian_906224_2022",
        "titulo_documento": "Oficio 906224 de 2022 sobre el artículo 51 de la Ley 1480 de 2011",
    }
    assert norma_de_resultado(r) is None


def test_codigos_por_nombre_y_la_primera_mencion_manda():
    assert norma("Código de Comercio, artículo 1058") == ("dec", 410, "1971")
    assert norma("Ley 769 de 2002 (Código vigente). El índice tiene la Ley 33 de 1986") == (
        "ley",
        769,
        "2002",
    )
    assert norma("no se") is None
