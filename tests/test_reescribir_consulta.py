"""Tests de la reescritura de consultas.

Todo con dobles: cargar el GGUF real (940 MB, ~1 min en CPU) no cabe en una
suite de tests, y lo que hay que probar aquí no es el modelo sino las guardas
alrededor — que son las que evitan que una reescritura mala reemplace lo que
escribió el usuario.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from index import reescribir_consulta as rc


@pytest.fixture
def modelo_falso(monkeypatch):
    """Sustituye cargar_modelo() por uno que devuelve el texto que se le diga."""
    estado = {"texto": "", "llamadas": 0, "kwargs": None}

    def fabricar(texto: str):
        estado["texto"] = texto

    def _cargar():
        def _modelo(prompt, **kwargs):
            estado["llamadas"] += 1
            estado["kwargs"] = kwargs
            estado["prompt"] = prompt
            return {"choices": [{"text": estado["texto"]}]}

        return _modelo

    import index.responder

    monkeypatch.setattr(index.responder, "cargar_modelo", _cargar)
    estado["fabricar"] = fabricar
    return estado


def test_reescribe_una_consulta_normal(modelo_falso):
    modelo_falso["fabricar"]("estabilidad laboral reforzada fuero de maternidad despido")
    salida = rc.reescribir("me pueden echar por estar embarazada")
    assert salida == "estabilidad laboral reforzada fuero de maternidad despido"


def test_descarta_salida_degenerada_y_devuelve_la_original(modelo_falso):
    """El fallo real observado: un modelo de 1.5B entra en bucle."""
    bucle = "contratación de trabajadores de aduanas " * 6
    modelo_falso["fabricar"](bucle)
    original = "quien contrata la gente en aduanas"
    assert rc.reescribir(original) == original


def test_quita_palabras_repetidas(modelo_falso):
    modelo_falso["fabricar"]("aduanas contratación empleo contratación aduanas personal")
    salida = rc.reescribir("quien contrata en aduanas")
    palabras = [p.lower() for p in salida.split()]
    assert len(palabras) == len(set(palabras))


def test_recorta_salidas_muy_largas(modelo_falso):
    modelo_falso["fabricar"](" ".join(f"palabra{i}" for i in range(60)))
    salida = rc.reescribir("algo")
    assert len(salida.split()) <= rc.MAX_PALABRAS


def test_salida_demasiado_corta_devuelve_la_original(modelo_falso):
    modelo_falso["fabricar"]("aduanas")
    original = "quien contrata la gente en aduanas"
    assert rc.reescribir(original) == original


def test_limpia_el_prefijo_terminos(modelo_falso):
    modelo_falso["fabricar"]('Términos: "recolección residuos poda árboles"')
    salida = rc.reescribir("quien recoge las ramas")
    assert salida.startswith("recolección")
    assert "Términos" not in salida


def test_se_queda_con_la_primera_linea(modelo_falso):
    modelo_falso["fabricar"]("recolección residuos poda\n\nConsulta: otra cosa")
    assert rc.reescribir("quien recoge las ramas") == "recolección residuos poda"


def test_consulta_vacia_no_llama_al_modelo(modelo_falso):
    assert rc.reescribir("   ") == "   "
    assert modelo_falso["llamadas"] == 0


def test_parametros_de_inferencia_son_los_declarados(modelo_falso):
    modelo_falso["fabricar"]("recolección residuos poda árboles")
    rc.reescribir("quien recoge las ramas")
    kwargs = modelo_falso["kwargs"]
    assert kwargs["max_tokens"] == rc.MAX_TOKENS
    assert kwargs["temperature"] == rc.TEMPERATURA
    assert kwargs["stop"] == rc.STOPS


def test_reescribir_o_original_no_propaga_fallos(monkeypatch):
    def _revienta(*_a, **_k):
        raise RuntimeError("falta el modelo")

    monkeypatch.setattr(rc, "reescribir", _revienta)
    assert rc.reescribir_o_original("una consulta") == "una consulta"
