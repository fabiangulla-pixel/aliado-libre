"""El troceo es una variable del experimento, y cambiarlo no puede ser silencioso.

El 12-sep-2026 quedo abierta una brecha de recall (33,5% el indice del 7-sep
contra 24,5% el actual) cuyo sospechoso es el rediseno del troceo. Para medirlo
cambiando UNA sola cosa hace falta poder elegir el troceo, construir el indice
aparte y que nadie pueda mezclar los dos por accidente.
"""

from __future__ import annotations

import pytest

from ingest import chunking
from ingest.chunking import TAMANIO_MAX, fragmentar
from ingest.schema import Documento


def _documento(texto: str) -> Documento:
    return Documento(
        id="doc-prueba",
        fuente="gestor_normativo",
        tipo="ley",
        identificador="LEY 1",
        titulo="Ley de prueba",
        fecha="2020-01-01",
        texto=texto,
        url_original="https://ejemplo.invalido/ley1",
    )


def _articulo_largo() -> str:
    parrafos = [f"Numeral {i}. " + "texto sustantivo del numeral. " * 12 for i in range(1, 9)]
    return "ARTÍCULO 1o. " + "\n\n".join(parrafos)


def test_por_defecto_trocea_por_parrafos(monkeypatch):
    monkeypatch.delenv("ALIADO_TROCEO", raising=False)
    assert chunking._modo_troceo() == chunking.TROCEO_POR_PARRAFOS


def test_modo_invalido_falla_en_vez_de_asumir(monkeypatch):
    monkeypatch.setenv("ALIADO_TROCEO", "porparrafo")
    with pytest.raises(ValueError, match="ALIADO_TROCEO"):
        fragmentar(_documento(_articulo_largo()))


def test_los_dos_troceos_dan_resultados_distintos(monkeypatch):
    texto = _articulo_largo()

    monkeypatch.setenv("ALIADO_TROCEO", chunking.TROCEO_POR_PARRAFOS)
    por_parrafos = [f.texto for f in fragmentar(_documento(texto))]

    monkeypatch.setenv("ALIADO_TROCEO", chunking.TROCEO_POR_TAMANIO)
    por_tamanio = [f.texto for f in fragmentar(_documento(texto))]

    # Si fueran iguales, el experimento no estaria cambiando nada y la medicion
    # saldria "sin diferencia" por una razon que no es la del experimento.
    assert por_parrafos != por_tamanio
    # El troceo por tamano solapa; el de parrafos no. Ese solape es justo la
    # hipotesis: mas contexto compartido entre fragmentos vecinos.
    assert por_tamanio[0][-50:] in por_tamanio[1]
    assert all(len(t) <= TAMANIO_MAX for t in por_parrafos + por_tamanio)


def test_ningun_troceo_pierde_texto(monkeypatch):
    """Lo que se arreglo el 11-sep no se puede perder al cambiar de modo."""
    texto = "ARTÍCULO 1o. " + "\n\n".join(["Numeral corto."] * 20 + ["Cuerpo largo. " * 120])
    for modo in chunking.TROCEOS_VALIDOS:
        monkeypatch.setenv("ALIADO_TROCEO", modo)
        unido = " ".join(f.texto for f in fragmentar(_documento(texto)))
        assert "Numeral corto." in unido, modo
        assert unido.count("Numeral corto.") >= 20, modo
