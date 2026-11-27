"""index/verificar_citas.py con catálogos falsos (no depende de los archivos del equipo)."""

import pytest

import index.resolver_citas as R
from index import verificar_citas as VC


@pytest.fixture(autouse=True)
def catalogos(monkeypatch):
    monkeypatch.setattr(
        "index.resolver_citas._cache",
        {
            "exacto": {
                "ley|142|1994": ["gestor_normativo:2752"],
                "ley|1943|2018": ["dian:tributario:ley_1943_2018"],
                "sentencia|T-760/08": ["corte_constitucional:29949"],
                "decreto|2663|1950": ["legalize_co_github:DECRETO-2663-1950"],
                "constitucion politica|1|1991": ["legalize_co_github:CONSTITUCION-POLITICA-CP-1991"],
            },
            "sin_anio": {
                "decreto|1072|": ["gestor_normativo:5343", "legalize_co_github:DECRETO-1072-2015"],
            },
            "titulos": {
                "gestor_normativo:2752": "Ley 142 de 1994",
                "dian:tributario:ley_1943_2018": "Ley 1943 de 2018",
                "corte_constitucional:29949": "Sentencia T-760/08",
                "legalize_co_github:DECRETO-2663-1950": "Código Sustantivo del Trabajo",
                "legalize_co_github:CONSTITUCION-POLITICA-CP-1991": "Constitución Política",
                "gestor_normativo:5343": "Decreto 1072 de 1980",
                "legalize_co_github:DECRETO-1072-2015": "Decreto 1072 de 2015",
            },
        },
    )
    monkeypatch.setattr(
        "index.vigencia._tabla",
        {
            "dian:tributario:ley_1943_2018": {
                "estado": "inexequible",
                "alcance": "documento",
                "texto": "Ley INEXEQUIBLE",
                "por": None,
            }
        },
    )
    monkeypatch.setattr("index.providencias.disponible", lambda: False)


def _por(r, reconocida):
    return next(c for c in r["citas"] if c["reconocida"].startswith(reconocida))


TEXTO = """Conforme al artículo 140 de la Ley 142 de 1994 y el artículo 64 del Código
Sustantivo del Trabajo, la sentencia T-760 de 2008, la Ley 1943 de 2018, el Decreto 1072,
la Ley 99999 de 2020 y la Constitución Política. Otra vez la Ley 142 de 1994."""


def test_estados_vigencia_y_articulo_mas_cercano():
    r = VC.verificar(TEXTO)
    assert _por(r, "Ley 142 de 1994")["articulo"] == "140"
    cst = _por(r, "Código Sustantivo")
    assert cst["articulo"] == "64" and cst["estado"] == "en_indice"  # cruza el salto de línea
    assert _por(r, "T-760/08")["estado"] == "en_indice"
    inex = _por(r, "Ley 1943 de 2018")
    assert inex["vigencia"]["estado"] == "inexequible" and r["resumen"]["no_rigen"] == 1
    assert _por(r, "Ley 99999")["estado"] == "no_en_indice"
    assert "no quiere decir que no exista" in _por(r, "Ley 99999")["aviso"].lower()
    assert _por(r, "Constitución")["estado"] == "en_indice"


def test_sin_anio_no_elige_y_no_lee_ids_numericos_como_años():
    c = _por(VC.verificar("según el Decreto 1072"), "Decreto 1072")
    assert c["estado"] == "sin_anio"
    assert [x["anio"] for x in c["candidatos"]] == ["2015", "1980"]  # el más reciente primero, sin "5343"


def test_repetidas_se_cuentan_y_corte_suprema_sin_catalogo_lo_dice():
    r = VC.verificar("Ley 142 de 1994. Ley 142 de 1994. Ver la SL131-2026.")
    assert _por(r, "Ley 142 de 1994")["veces"] == 2
    assert _por(r, "SL131-2026")["estado"] == "sin_catalogo"


def test_texto_sin_citas_y_prosa_que_no_es_cita():
    """Negativa: «la constitución de una sociedad» o «T 2» no son citas."""
    r = VC.verificar("Quiero saber sobre la constitución de una sociedad y el punto T 2 del contrato.")
    assert r["citas"] == []


def test_url_oficial_del_gestor():
    c = _por(VC.verificar("Ley 142 de 1994"), "Ley 142")
    assert c["documentos"][0]["url"].endswith("norma.php?i=2752")


def test_anio_de_documento_del_resolver():
    assert R.anio_de_documento("gestor_normativo:5343", "Decreto 1072 de 1980") == "1980"
    assert R.anio_de_documento("legalize_co_github:DECRETO-1072-2015", "") == "2015"
    assert R.anio_de_documento("gestor_normativo:5343", "Sin año") == "?"
