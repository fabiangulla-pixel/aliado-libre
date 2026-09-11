"""Los prefijos query:/passage: no pueden desaparecer en silencio.

El 9-sep-2026 el indice se construyo sin "passage: " mientras las consultas si
llevaban "query: ", y el recall se desplomo sin que nada fallara. La deteccion
por subcadena ("e5" en el nombre del modelo) basta para un identificador del
Hub, pero no para una ruta local: un modelo afinado guardado como
"modelos/afinado_v2" repetiria aquel fallo exacto.
"""

import importlib
import sys
import warnings

import pytest


def _recargar(monkeypatch, modelo: str, prefijos: str | None):
    monkeypatch.setenv("ALIADO_MODELO_EMBEDDINGS", modelo)
    if prefijos is None:
        monkeypatch.delenv("ALIADO_PREFIJOS", raising=False)
    else:
        monkeypatch.setenv("ALIADO_PREFIJOS", prefijos)
    for nombre in [k for k in list(sys.modules) if k.startswith("index")]:
        del sys.modules[nombre]
    return importlib.import_module("index.buscar")


@pytest.mark.parametrize(
    ("modelo", "prefijos", "esperado"),
    [
        ("intfloat/multilingual-e5-large", None, "query: "),
        ("C:/x/modelos/e5_afinado", None, "query: "),
        ("C:/x/modelos/afinado_v2", "e5", "query: "),  # a mano, contra la heuristica
        ("C:/x/modelos/afinado_v2", "ninguno", ""),
        ("sentence-transformers/all-MiniLM-L6-v2", None, ""),
    ],
)
def test_prefijos_segun_modelo(monkeypatch, modelo, prefijos, esperado):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        buscar = _recargar(monkeypatch, modelo, prefijos)
    assert buscar.PREFIJO_CONSULTA == esperado
    assert buscar.PREFIJO_PASAJE == ("passage: " if esperado else "")


def test_ruta_local_sin_pista_avisa_en_vez_de_callar(monkeypatch):
    """El caso que repetiria el fallo del 9-sep tiene que hacer ruido."""
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        buscar = _recargar(monkeypatch, "C:/x/modelos/afinado_v2", None)
    assert buscar.PREFIJO_CONSULTA == ""
    assert any(issubclass(a.category, RuntimeWarning) for a in avisos), "se quedo callado"
    assert any("ALIADO_PREFIJOS" in str(a.message) for a in avisos), "el aviso no dice como arreglarlo"


def test_el_identificador_del_hub_no_avisa(monkeypatch):
    """Solo avisa en rutas locales: el caso normal no debe generar ruido."""
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        _recargar(monkeypatch, "intfloat/multilingual-e5-large", None)
    assert not [a for a in avisos if "ALIADO_PREFIJOS" in str(a.message)]
