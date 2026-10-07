from ingest.anonimizar import MARCA_DESTINATARIO, enmascarar_destinatario


def test_quita_bloque_del_destinatario_hasta_la_referencia():
    texto = (
        "CONCEPTO 87 DE 2010\nSeñor\nULISES SÁNCHEZ\nAlcalde Municipal\nCalle Antonio Nariño\n"
        "Lorica - Córdoba\nRef.: Su solicitud de concepto\nSe basa la consulta en..."
    )
    salida = enmascarar_destinatario(texto)
    assert "ULISES" not in salida and "Antonio Nariño" not in salida
    assert MARCA_DESTINATARIO in salida
    assert "Ref.: Su solicitud de concepto\nSe basa la consulta en..." in salida


def test_variantes_de_saludo_y_vocativo():
    salida = enmascarar_destinatario("Señor (a)\nPEPE PÉREZ\nRef: x\nRespetado señor (a) Pepe Pérez:\nTexto")
    assert "Pepe" not in salida and "PEPE" not in salida
    assert "Respetado señor (a):" in salida


def test_correos_y_telefonos():
    salida = enmascarar_destinatario("escribir a luz@hotmail.com o al cel. 300 123 4567 para más")
    assert "@" not in salida and "4567" not in salida


def test_sin_referencia_no_se_come_el_cuerpo():
    texto = "Señora\n" + "\n".join(f"párrafo {i} del concepto" for i in range(30))
    assert enmascarar_destinatario(texto) == texto


def test_idempotente_y_no_toca_el_articulado():
    texto = "ARTÍCULO 130. Las empresas podrán suspender el servicio. Ley 142 de 1994."
    assert enmascarar_destinatario(texto) == texto
    once = enmascarar_destinatario("Señora\nANA\nAsunto: x\ncuerpo")
    assert enmascarar_destinatario(once) == once
