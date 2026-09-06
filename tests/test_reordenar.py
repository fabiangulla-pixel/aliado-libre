"""El reranker reordena, y si falla no rompe la búsqueda.

Con dobles: cargar `bge-reranker-v2-m3` son ~2,2 GB y varios segundos, y lo que
hay que probar aquí no es el modelo sino el contrato alrededor — que una mejora
opcional nunca convierta una búsqueda que funciona en un error.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from index import reordenar as R


@pytest.fixture(autouse=True)
def _limpiar_estado():
    """Cada test empieza sin modelo cargado: el módulo cachea a propósito."""
    R._modelo = None
    R._fallo = None
    yield
    R._modelo = None
    R._fallo = None


def _resultados(*textos):
    return [{"id": f"f{i}", "texto": t, "puntaje": 0.05 - i * 0.001} for i, t in enumerate(textos)]


def _modelo_falso(monkeypatch, puntajes, registro=None):
    class _Cross:
        def __init__(self, *a, **k):
            pass

        def predict(self, pares):
            if registro is not None:
                registro.extend(pares)
            return puntajes[: len(pares)]

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=_Cross))


def test_reordena_por_pertinencia(monkeypatch):
    _modelo_falso(monkeypatch, [0.1, 0.9, 0.5])
    salida = R.reordenar("cuánto dura un encargo", _resultados("a", "b", "c"))
    assert [r["id"] for r in salida] == ["f1", "f2", "f0"]
    assert salida[0]["puntaje_reranker"] == 0.9


def test_conserva_los_campos_del_fragmento(monkeypatch):
    _modelo_falso(monkeypatch, [0.9, 0.1])
    salida = R.reordenar("consulta", _resultados("a", "b"))
    assert salida[0]["texto"] == "a"
    assert "puntaje" in salida[0]


def test_recibe_la_consulta_junto_al_pasaje(monkeypatch):
    """Ese es el punto del cross-encoder: leer los dos a la vez."""
    registro = []
    _modelo_falso(monkeypatch, [0.5, 0.4], registro)
    R.reordenar("mi consulta", _resultados("texto uno", "texto dos"))
    assert registro[0] == ("mi consulta", "texto uno")


def test_sin_modelo_devuelve_el_orden_original(monkeypatch):
    def _revienta(*a, **k):
        raise OSError("no se pudo descargar el modelo")

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=_revienta))
    original = _resultados("a", "b", "c")
    assert R.reordenar("consulta", original) == original
    assert R.disponible() is False


def test_un_fallo_al_predecir_no_rompe_la_busqueda(monkeypatch):
    class _Cross:
        def __init__(self, *a, **k):
            pass

        def predict(self, pares):
            raise RuntimeError("se quedó sin memoria")

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=_Cross))
    original = _resultados("a", "b")
    assert R.reordenar("consulta", original) == original


def test_lista_vacia_o_consulta_vacia_no_llaman_al_modelo(monkeypatch):
    registro = []
    _modelo_falso(monkeypatch, [0.9], registro)
    assert R.reordenar("consulta", []) == []
    assert R.reordenar("   ", _resultados("a")) == _resultados("a")
    assert registro == []


def test_el_modelo_se_carga_una_sola_vez(monkeypatch):
    cargas = []

    class _Cross:
        def __init__(self, *a, **k):
            cargas.append(1)

        def predict(self, pares):
            return [0.5] * len(pares)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=_Cross))
    R.reordenar("a", _resultados("x"))
    R.reordenar("b", _resultados("y"))
    assert len(cargas) == 1


def test_solo_reordena_la_ventana_y_conserva_el_resto(monkeypatch):
    """Reordenar 500 candidatos costaría más que la búsqueda entera."""
    monkeypatch.setattr(R, "CANDIDATOS", 2)
    _modelo_falso(monkeypatch, [0.1, 0.9])
    salida = R.reordenar("consulta", _resultados("a", "b", "c", "d"))
    assert [r["id"] for r in salida[:2]] == ["f1", "f0"]
    assert [r["id"] for r in salida[2:]] == ["f2", "f3"]


def test_k_recorta_la_salida(monkeypatch):
    _modelo_falso(monkeypatch, [0.1, 0.9, 0.5])
    salida = R.reordenar("consulta", _resultados("a", "b", "c"), k=2)
    assert len(salida) == 2


def test_no_esta_conectado_a_la_busqueda_todavia():
    """Se mide antes de encenderlo: hoy `buscar()` no lo llama."""
    fuente = (Path(__file__).resolve().parent.parent / "index" / "buscar.py").read_text(encoding="utf-8")
    assert "reordenar" not in fuente
