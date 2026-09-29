"""Métricas de rango del banco de ensayos (finetune/eval/lab_recuperacion.py)."""

import pytest

from finetune.eval.lab_recuperacion import metricas_rango, rango_documento


def test_rango_por_documento_no_por_fragmento():
    orden = ["ley_a::frag3", "ley_b::frag0", "ley_b::frag9"]
    assert rango_documento(orden, "ley_b") == 2
    assert rango_documento(orden, "ley_c") is None


def test_metricas_de_rango():
    m = metricas_rango([1, 3, 7, None])
    assert m["recall@1"] == 0.25
    assert m["recall@5"] == 0.5
    assert m["recall@10"] == 0.75
    assert m["mrr@10"] == pytest.approx((1 + 1 / 3 + 1 / 7) / 4)


def test_mrr_ignora_lo_que_cae_fuera_de_diez():
    assert metricas_rango([11])["mrr@10"] == 0
