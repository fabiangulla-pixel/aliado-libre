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
    R._gpu = None
    yield
    R._modelo = None
    R._fallo = None
    R._gpu = None


def _resultados(*textos):
    return [{"id": f"f{i}", "texto": t, "puntaje": 0.05 - i * 0.001} for i, t in enumerate(textos)]


def _modelo_falso(monkeypatch, puntajes, registro=None, opciones=None):
    class _Cross:
        def __init__(self, *a, **k):
            if opciones is not None:
                opciones.update(k)

        def predict(self, pares, **kwargs):
            if registro is not None:
                registro.extend(pares)
            if opciones is not None:
                opciones.update(kwargs)
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


def test_esta_conectado_a_la_busqueda_local():
    """Este test decía lo contrario mientras el reranker se medía sin usarse.
    Ahora `buscar()` sí lo llama, y el contrato de esa llamada se prueba en
    tests/test_buscar_reordena.py."""
    fuente = (Path(__file__).resolve().parent.parent / "index" / "buscar.py").read_text(encoding="utf-8")
    assert "from index.reordenar import CANDIDATOS, activo, reordenar" in fuente


# -- cuándo se enciende ----------------------------------------------------
#
# APAGADO POR DEFECTO desde el 12-sep-2026, aunque haya GPU de sobra.
#
# Se encendía solo con GPU por los +10 puntos de recall@5 medidos el 7-sep. Esa
# medición usaba consultas redactadas A PARTIR del fragmento que debían
# recuperar. Con consultas escritas como habla la gente, el reordenador empeora:
# 27% sin él, 23% con ventana 40, 20% con ventana 120. Y el caso que lo enseña
# mejor que la tabla: ante «puedo tener mi herencia antes de que mueran mis
# padres» la fusión devuelve primero el Código Civil (LEY-84-1873) y el
# reordenador lo saca del top-5 para poner un decreto de 1938 sobre la Caja de
# Auxilios de la Policía.


def test_apagado_por_defecto_aunque_haya_gpu(monkeypatch):
    """Tener con qué reordenar no es razón para hacerlo: está medido que daña."""
    monkeypatch.delenv("ALIADO_RERANKER_ACTIVO", raising=False)
    monkeypatch.setattr(R, "_hay_gpu", lambda: True)
    assert R.activo() is False


def test_sin_gpu_tambien_apagado(monkeypatch):
    monkeypatch.delenv("ALIADO_RERANKER_ACTIVO", raising=False)
    monkeypatch.setattr(R, "_hay_gpu", lambda: False)
    assert R.activo() is False


def test_se_puede_encender_a_mano_para_volver_a_medirlo(monkeypatch):
    """El código se conserva: el margen existe, este reordenador no lo cobra."""
    monkeypatch.setenv("ALIADO_RERANKER_ACTIVO", "1")
    monkeypatch.setattr(R, "_hay_gpu", lambda: False)
    assert R.activo() is True


@pytest.mark.parametrize("valor", ["0", "false", "no", ""])
def test_un_apagado_explicito_sigue_apagando(monkeypatch, valor):
    """El servidor del índice fija "0" para quedarse fuera de la regla.

    La cadena vacía es "no haber dicho nada", y desde el 12-sep-2026 eso ya no
    significa "mira si hay GPU" sino "apagado": el defecto cambió.
    """
    monkeypatch.setenv("ALIADO_RERANKER_ACTIVO", valor)
    monkeypatch.setattr(R, "_hay_gpu", lambda: True)
    assert R.activo() is False


@pytest.mark.parametrize("valor", ["1", "true", "si", "sí", "SI", " 1 "])
def test_un_encendido_explicito_gana_a_la_ausencia_de_gpu(monkeypatch, valor):
    monkeypatch.setenv("ALIADO_RERANKER_ACTIVO", valor)
    monkeypatch.setattr(R, "_hay_gpu", lambda: False)
    assert R.activo() is True


def test_sin_torch_no_hay_gpu_y_no_revienta(monkeypatch):
    """En el .exe no está torch: preguntarle a la GPU no puede tumbar nada."""
    import builtins

    real = builtins.__import__

    def sin_torch(nombre, *a, **k):
        if nombre == "torch":
            raise ImportError("No module named 'torch'")
        return real(nombre, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sin_torch)
    monkeypatch.delenv("ALIADO_RERANKER_ACTIVO", raising=False)
    assert R._hay_gpu() is False
    assert R.activo() is False


def test_la_gpu_se_pregunta_una_sola_vez(monkeypatch):
    """Importar torch no es gratis y activo() se llama en cada búsqueda."""
    veces = []

    class _Torch:
        class cuda:
            @staticmethod
            def is_available():
                veces.append(1)
                return True

    monkeypatch.setitem(sys.modules, "torch", _Torch)
    monkeypatch.setenv("ALIADO_RERANKER_ACTIVO", "1")
    # Con el reordenador apagado por defecto ya ni se pregunta por la GPU; se
    # enciende a mano para comprobar que, cuando se usa, sigue sin importar
    # torch en cada búsqueda.
    assert R.activo() is True
    assert R.activo() is True
    assert len(veces) <= 1


# -- media precisión: 2,9x más rápido y el mismo orden ----------------------


def test_en_gpu_carga_en_media_precision(monkeypatch):
    """Medido sobre 60 consultas reales: 3,49 s -> 1,19 s por consulta, con el
    mismo top-5 en el mismo orden en 60 de 60. Los +10 puntos de recall@5 se
    heredan; no es una aproximación por validar."""
    import torch

    monkeypatch.setattr(R, "_hay_gpu", lambda: True)
    opciones: dict = {}
    _modelo_falso(monkeypatch, [0.5], opciones=opciones)
    R.cargar_reranker()
    assert opciones["model_kwargs"] == {"torch_dtype": torch.float16}


def test_en_cpu_no_pide_media_precision(monkeypatch):
    """En CPU la media precisión no está acelerada y sale más lenta."""
    monkeypatch.setattr(R, "_hay_gpu", lambda: False)
    opciones: dict = {}
    _modelo_falso(monkeypatch, [0.5], opciones=opciones)
    R.cargar_reranker()
    assert "model_kwargs" not in opciones


def test_los_candidatos_van_en_un_solo_lote(monkeypatch):
    """El batch por defecto (32) partiría los 40 en dos sin ganar nada."""
    opciones: dict = {}
    _modelo_falso(monkeypatch, [0.5] * 40, opciones=opciones)
    R.reordenar("consulta", _resultados(*[f"t{i}" for i in range(40)]))
    assert opciones["batch_size"] == 40
