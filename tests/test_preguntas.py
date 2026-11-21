import numpy as np

import index.preguntas as pr


def _preparar(monkeypatch, peso=1.0):
    emb = np.array([[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    monkeypatch.setattr(pr, "_matriz", emb)
    monkeypatch.setattr(pr, "_fragmentos", np.array(["a::frag0", "a::frag0", "b::frag1", "c::frag2"]))
    monkeypatch.setattr(pr, "PESO_PREGUNTAS", peso)


def test_apagado_por_defecto_no_devuelve_nada(monkeypatch):
    _preparar(monkeypatch, peso=0.0)
    assert pr.lista_preguntas([1, 0, 0], 5) == []


def test_ordena_por_parecido_y_no_repite_fragmento(monkeypatch):
    _preparar(monkeypatch)
    assert pr.lista_preguntas([1, 0.05, 0], 5) == ["a::frag0", "b::frag1", "c::frag2"]


def test_respeta_n(monkeypatch):
    _preparar(monkeypatch)
    assert pr.lista_preguntas([0, 0, 1], 1) == ["c::frag2"]
