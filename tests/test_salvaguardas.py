from index.salvaguardas import quitar_numeros_inventados


def test_borra_numero_de_norma_inventado():
    limpio = quitar_numeros_inventados("reajuste del canon Ley 820 de 2003", "me suben el arriendo")
    assert "820" not in limpio and "2003" not in limpio
    assert "canon" in limpio
    assert not limpio.lower().endswith("ley")


def test_conserva_el_numero_que_escribio_el_usuario():
    limpio = quitar_numeros_inventados("arrendamiento Ley 820 de 2003", "que dice la ley 820")
    assert "820" in limpio
    assert "2003" not in limpio


def test_borra_sentencias_y_articulos_inventados():
    limpio = quitar_numeros_inventados(
        "estabilidad reforzada sentencia T-025 artículo 239", "me echaron embarazada"
    )
    assert "T-025" not in limpio and "239" not in limpio
    assert "estabilidad reforzada" in limpio


def test_sin_numeros_no_cambia():
    assert (
        quitar_numeros_inventados("despido de trabajadora embarazada", "x")
        == "despido de trabajadora embarazada"
    )
