from ingest.chunking import TAMANIO_MAX, fragmentar
from ingest.schema import Documento


def _doc(texto: str) -> Documento:
    return Documento(
        id="test:1",
        fuente="gestor_normativo",
        tipo="decreto",
        identificador="Decreto de prueba",
        titulo="Decreto de prueba",
        fecha="2020-01-01",
        texto=texto,
        url_original="https://example.test/1",
    )


def test_fragmenta_por_articulo_cuando_existe_estructura():
    texto = (
        "ARTÍCULO 1. Primer artículo con contenido relevante.\n"
        "ARTÍCULO 2. Segundo artículo con otro contenido distinto.\n"
        "ARTÍCULO 3. Tercer artículo final."
    )
    fragmentos = fragmentar(_doc(texto))
    assert len(fragmentos) == 3
    assert fragmentos[0].texto.startswith("ARTÍCULO 1")
    assert fragmentos[1].texto.startswith("ARTÍCULO 2")


def test_fragmenta_por_tamanio_sin_estructura_de_articulos():
    texto = "palabra " * 1000  # ~8000 caracteres, sin marcadores de artículo
    fragmentos = fragmentar(_doc(texto))
    assert len(fragmentos) > 1
    for f in fragmentos:
        assert len(f.texto) <= 1500 + 1  # tolerancia mínima por strip


def test_documento_corto_no_se_fragmenta():
    fragmentos = fragmentar(_doc("Texto breve sin artículos."))
    assert len(fragmentos) == 1


def test_fragmentos_preservan_metadata_del_documento():
    fragmentos = fragmentar(_doc("ARTÍCULO 1. Contenido."))
    assert fragmentos[0].documento_id == "test:1"
    assert fragmentos[0].fuente == "gestor_normativo"
    assert fragmentos[0].url_original == "https://example.test/1"


def test_ids_de_fragmentos_son_unicos():
    texto = "ARTÍCULO 1. Uno.\nARTÍCULO 2. Dos.\nARTÍCULO 3. Tres."
    fragmentos = fragmentar(_doc(texto))
    ids = [f.id for f in fragmentos]
    assert len(ids) == len(set(ids))


# --- Regresiones del 10-sep-2026 -------------------------------------------
# El limpiador de ceremonial cortaba por "FIRMA", "MINISTRO" y "PRESIDENTE"
# sueltos, sin límite de palabra ni ancla de final. Sobre el corpus real se
# perdía el 77% de los caracteres y el 12,2% de los documentos salía con cero
# fragmentos, o sea desaparecía del índice sin dejar rastro.

_CUERPO = "ARTÍCULO 1. " + ("contenido normativo que debe sobrevivir. " * 40)


def test_una_palabra_que_contiene_firma_no_trunca_el_documento():
    texto = "El juez confirma lo resuelto. " + _CUERPO
    fragmentos = fragmentar(_doc(texto))
    assert "debe sobrevivir" in fragmentos[-1].texto
    assert sum(len(f.texto) for f in fragmentos) > len(texto) * 0.9


def test_mencionar_al_presidente_o_al_ministro_no_trunca_el_documento():
    for mencion in ("El Presidente de la República decreta: ", "El Ministro reglamentará. "):
        fragmentos = fragmentar(_doc(mencion + _CUERPO))
        assert sum(len(f.texto) for f in fragmentos) > len(_CUERPO) * 0.9, mencion


def test_la_formula_de_cierre_al_final_si_se_recorta():
    fragmentos = fragmentar(_doc(_CUERPO + "\nCOMUNÍQUESE Y CÚMPLASE\nEl Ministro de Hacienda"))
    texto = " ".join(f.texto for f in fragmentos)
    assert "COMUNÍQUESE" not in texto.upper()
    assert "debe sobrevivir" in texto


def test_la_formula_al_principio_no_es_un_cierre():
    texto = "COMUNÍQUESE Y CÚMPLASE\n" + _CUERPO
    fragmentos = fragmentar(_doc(texto))
    assert "debe sobrevivir" in " ".join(f.texto for f in fragmentos)


def test_ningun_documento_con_texto_sale_sin_fragmentos():
    for texto in ("Resolución breve.", "ARTÍCULO 1. Corto.", "Firma del ponente.", "El Presidente."):
        assert fragmentar(_doc(texto)), f"documento perdido: {texto!r}"


def test_la_formula_dado_en_tambien_se_recorta():
    """La rama "DADO EN ... a los" del patron de cierre tiene que funcionar.

    Estuvo muerta sin que nadie lo notara: al escribirla, los `\b` acabaron como
    caracteres de retroceso reales (0x08) dentro del archivo, asi que la rama
    exigia un byte que ningun documento contiene y nunca coincidia. Los tests
    existentes solo ejercitaban la rama de COMUNIQUESE, asi que pasaban.
    """
    texto = _CUERPO + "\nDADO EN BOGOTA, D.C., a los 5 dias del mes de marzo de 2020.\nEl Ministro"
    fragmentos = fragmentar(_doc(texto))
    unido = " ".join(f.texto for f in fragmentos)
    assert "debe sobrevivir" in unido
    assert "DADO EN" not in unido.upper()


def test_el_troceo_no_borra_texto():
    """Trocear no puede perder contenido, solo repartirlo (o duplicarlo por solape).

    La version del 9-sep-2026 descartaba los parrafos de menos de 150 caracteres
    dentro de un articulo largo. En texto juridico esos parrafos son numerales y
    clausulas operativas. Sobre el corpus real, `legalize_co_github` conservaba
    el 82,3% de su texto; el agregado no lo delataba porque el solape duplica
    texto en otras fuentes y compensaba la perdida.
    """
    parrafos = [
        "ARTÍCULO 5. Definiciones aplicables al presente decreto. " + "Texto de relleno. " * 60,
        "1. Beneficiario.",  # corto a proposito: antes desaparecia
        "2. Autoridad competente.",
        "PARÁGRAFO. La entidad reglamentará la materia. " + "Mas relleno. " * 60,
        "3. Vigencia inmediata.",
    ]
    texto = "\n\n".join(parrafos)
    fragmentos = fragmentar(_doc(texto))
    unido = " ".join(f.texto for f in fragmentos)
    for corto in ("1. Beneficiario.", "2. Autoridad competente.", "3. Vigencia inmediata."):
        assert corto in unido, f"el troceo borro un parrafo corto: {corto!r}"


def test_ningun_fragmento_supera_el_tope_declarado():
    """Un parrafo mas largo que el tope se trocea; antes se emitia entero."""
    texto = "ARTÍCULO 1. " + ("palabra " * 900)  # un solo parrafo de ~7.200 caracteres
    for f in fragmentar(_doc(texto)):
        assert len(f.texto) <= TAMANIO_MAX + 1, f"fragmento de {len(f.texto)} caracteres"
