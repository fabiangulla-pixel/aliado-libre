from ingest.chunking import fragmentar
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
