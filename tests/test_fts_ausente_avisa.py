"""El índice léxico ausente tiene que hacer ruido.

El 9-sep-2026 el reindexado borró `index/fts_index.db` y no lo reconstruyó. La
búsqueda siguió respondiendo, solo que con la mitad vectorial y con los pesos
del RRF calibrados para una fusión que ya no ocurría. Nadie se enteró hasta que
el recall@5 se midió en 0,5%. Degradarse en silencio es el defecto; avisar es
el arreglo.
"""

import warnings

import pytest

from index import buscar as modulo_buscar


@pytest.fixture
def _sin_aviso_previo():
    anterior = modulo_buscar.IndiceBusqueda._aviso_fts_dado
    modulo_buscar.IndiceBusqueda._aviso_fts_dado = False
    yield
    modulo_buscar.IndiceBusqueda._aviso_fts_dado = anterior


def _indice_sin_abrir() -> modulo_buscar.IndiceBusqueda:
    """Una instancia sin tocar Chroma: solo interesa la rama del FTS."""
    indice = object.__new__(modulo_buscar.IndiceBusqueda)
    import threading

    indice._local = threading.local()
    return indice


def test_avisa_cuando_falta_el_indice_lexico(tmp_path, monkeypatch, _sin_aviso_previo):
    monkeypatch.setattr(modulo_buscar, "DB_FTS", tmp_path / "no_existe.db")
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        assert _indice_sin_abrir()._fts is None
    assert any(issubclass(a.category, RuntimeWarning) for a in avisos), "se degradó sin avisar"
    assert any("FTS5" in str(a.message) for a in avisos)


def test_el_aviso_no_se_repite_en_cada_consulta(tmp_path, monkeypatch, _sin_aviso_previo):
    monkeypatch.setattr(modulo_buscar, "DB_FTS", tmp_path / "no_existe.db")
    indice = _indice_sin_abrir()
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        for _ in range(5):
            assert indice._fts is None
    assert len(avisos) == 1, "un aviso por proceso, no uno por consulta"
