"""Citas exactas: reconocerlas sin confundir la prosa de quien pregunta, y resolverlas contra el corpus."""

import pytest

from index import resolver_citas as rc
from index.citas import parsear_cita, parsear_radicado


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("art. 64 del CST", ("decreto", "2663", "1950", "64")),
        ("artículo 771-5 del Estatuto Tributario", ("decreto", "624", "1989", "771-5")),
        ("Ley 1480 de 2011 artículo 51", ("ley", "1480", "2011", "51")),
        ("artículo 86 de la Constitución", ("constitucion politica", "1", "1991", "86")),
        ("Decreto 1072", ("decreto", "1072", None, None)),
        # Gana la referencia que aparece antes.
        ("art. 217 del Código Civil, modificado por la Ley 1060 de 2006", ("ley", "84", "1873", "217")),
        ("art. 5 de la Ley 1060 de 2006, que modifica el Código Civil", ("ley", "1060", "2006", "5")),
    ],
)
def test_normas(texto, esperado):
    c = parsear_cita(texto)
    assert (c.tipo, c.numero, c.anio, c.articulo) == esperado


@pytest.mark.parametrize(
    "texto, sentencia",
    [
        ("T-760/08", "T-760/08"),
        ("C-351 de 2013", "C-351/13"),
        ("SU-123/20", "SU-123/20"),
        ("T-099-24", "T-099/24"),
        ("Sentencia A. 692/21", "A-692/21"),
        ("la sentencia T 760 de 2008", "T-760/08"),
    ],
)
def test_sentencias(texto, sentencia):
    assert parsear_cita(texto).sentencia == sentencia


@pytest.mark.parametrize(
    "texto",
    [
        "me echaron del trabajo estando enfermo",
        "le pago a 3/4 partes de la deuda",
        "me citaron a 15 de 2023",  # «a» suelta no es un auto
        "la Corte Constitucional dijo algo",  # «Constitucional» no es la Constitución
    ],
)
def test_prosa_no_es_cita(texto):
    c = parsear_cita(texto)
    assert c is None or c.tipo != "auto" and c.tipo != "constitucion politica"


def test_radicado_de_alta_corte_y_de_origen():
    r = parsear_radicado("rad. 11001-03-15-000-2020-00123-00 (AC)")
    assert r.corporacion == "consejo-de-estado" and r.departamento == "Bogotá D.C."
    # 3103 es un juzgado civil del circuito: no se le atribuye una alta corte.
    assert parsear_radicado("11001310300320190012300").corporacion == "desconocida"
    assert parsear_radicado("11001-03-15-000-1800-00123-00") is None  # año imposible


# --- resolver contra un corpus falso -----------------------------------------


class _Coleccion:
    def __init__(self, docs):
        self.docs = docs

    def get(self, where, include, limit):
        frags = self.docs.get(where["documento_id"], [])
        return {
            "ids": [f"{where['documento_id']}::frag{i}" for i in range(len(frags))],
            "documents": frags,
            "metadatas": [
                {"orden": i, "titulo_documento": "T", "documento_id": where["documento_id"]}
                for i in range(len(frags))
            ],
        }


@pytest.fixture()
def catalogo(monkeypatch):
    cat = {
        "exacto": {
            "decreto|2663|1950": ["legalize_co_github:DECRETO-2663-1950"],
            "sentencia|T-760/08": ["corte_constitucional:29949"],
        },
        "sin_anio": {
            "decreto|1072|": ["legalize_co_github:DECRETO-1072-2015", "legalize_co_github:DECRETO-1072-1999"],
        },
        "titulos": {"legalize_co_github:DECRETO-1072-2015": "Decreto Único Laboral"},
    }
    monkeypatch.setattr(rc, "_cache", cat)
    monkeypatch.setattr("index.vigencia.anotar", lambda r: r)
    return cat


def test_resuelve_el_articulo_aunque_el_texto_venga_mal_codificado(catalogo):
    col = _Coleccion(
        {
            "legalize_co_github:DECRETO-2663-1950": [
                "ARTÃ\x8dCULO 63. Otro",
                "ARTÃ\x8dCULO 64. TERMINACION UNILATERAL",
            ]
        }
    )
    r = rc.resolver("art. 64 del CST", col)
    assert [f["id"] for f in r.resultados] == ["legalize_co_github:DECRETO-2663-1950::frag1"]
    assert r.resultados[0]["cita_exacta"] is True


def test_articulo_640_no_es_el_64(catalogo):
    col = _Coleccion(
        {"legalize_co_github:DECRETO-2663-1950": ["Artículo 640. Otra cosa", "Artículo 64-1. Tampoco"]}
    )
    r = rc.resolver("art. 64 del CST", col)
    assert "no encontré el artículo 64" in r.aviso


def test_sin_anio_pide_el_anio_en_vez_de_elegir(catalogo):
    r = rc.resolver("Decreto 1072", _Coleccion({}))
    assert not r.resultados
    assert [c["anio"] for c in r.candidatos] == ["1999", "2015"]


def test_cita_ausente_dice_que_no_esta_en_el_indice(catalogo):
    r = rc.resolver("Ley 99999 de 2020", _Coleccion({}))
    assert "no está en el índice" in r.aviso


def test_sin_cita_no_hace_nada(catalogo):
    assert rc.resolver("me echaron del trabajo", _Coleccion({})).cita is None


def test_catalogo_ignora_constituciones_viejas():
    assert rc._cita_de_documento("legalize_co_github:CONSTITUCION-POLITICA-CP-1886-1886", "x") is None
    assert rc._cita_de_documento("legalize_co_github:CONSTITUCION-POLITICA-CP-1991", "x").anio == "1991"
    assert rc._cita_de_documento("gestor_normativo:1", "Constitución Política de 1886") is None


def test_titulo_largo_no_trunca_el_anio():
    # "Sentencia de Unificación de Revisión de Tutela SU-499 de 2024" tiene 61
    # caracteres: con el corte viejo en 60 perdía la última cifra del año y
    # SU-499/24 se catalogaba como SU-499/02.
    titulo = "Sentencia de Unificación de Revisión de Tutela SU-499 de 2024"
    cita = rc._cita_de_documento("dian:tributario:su-499_2024", titulo)
    assert cita.sentencia == "SU-499/24"
