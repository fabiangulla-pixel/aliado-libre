"""El índice local reordena por su cuenta, y el remoto no puede hacerlo.

Reordenar con el cross-encoder era la única mejora de recuperación confirmada
en datos apartados (+10 puntos de recall@5) y durante meses solo estuvo cableada
en el servidor del índice: quien usaba el programa en su equipo buscaba sin
ella. Al bajarla a `IndiceBusqueda.buscar` la heredan la GUI, el servidor MCP y
`responder`, y lo que hay que proteger es el contrato de ese punto único —
cuántos candidatos se piden, cuántos se devuelven y que apagado no cueste nada.

Se carga index/buscar.py con chromadb y sentence_transformers falsos: importarlo
de verdad arrastraría torch, que es caro y ajeno a lo que se prueba aquí.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from index import reordenar as R  # noqa: E402


def _cargar_buscar():
    class _Falso:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, _nombre):
            return _Falso()

        def __call__(self, *a, **k):
            return _Falso()

    falsos = {"chromadb": _Falso(), "sentence_transformers": _Falso()}
    originales = {n: sys.modules.get(n) for n in falsos}
    sys.modules.update(falsos)
    try:
        spec = importlib.util.spec_from_file_location("_buscar_reordena", RAIZ / "index" / "buscar.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        for nombre, original in originales.items():
            if original is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = original
    return modulo


@pytest.fixture
def indice():
    """Instancia sin __init__ (no hay 16 GB de índice aquí) con la búsqueda
    cruda sustituida por un espía que devuelve tantos resultados como se pidan."""
    modulo = _cargar_buscar()
    obj = modulo.IndiceBusqueda.__new__(modulo.IndiceBusqueda)
    obj.pedidos = []

    def _crudo(consulta, k=8, fuentes=None):
        obj.pedidos.append((k, fuentes))
        return [{"id": f"f{i}", "texto": f"texto {i}", "puntaje": 0.05 - i * 0.001} for i in range(k)]

    obj._buscar_crudo = _crudo
    return obj


def test_apagado_pide_exactamente_lo_que_devuelve(indice, monkeypatch):
    """Sin reordenar no debe pedir candidatos de más: sería tiempo de búsqueda
    gastado en resultados que se tiran."""
    monkeypatch.setattr(R, "activo", lambda: False)
    salida = indice.buscar("tutela", k=5)
    assert indice.pedidos == [(5, None)]
    assert len(salida) == 5


def test_encendido_ensancha_la_ventana_y_devuelve_los_k_pedidos(indice, monkeypatch):
    """El reranker solo puede mejorar el orden de lo que recibe: pedirle 5 y
    reordenar 5 no cambiaría nada. La ventana medida es 40."""
    monkeypatch.setattr(R, "activo", lambda: True)
    monkeypatch.setattr(R, "reordenar", lambda consulta, resultados, k=None: list(reversed(resultados))[:k])

    salida = indice.buscar("tutela", k=5)

    assert indice.pedidos == [(R.CANDIDATOS, None)]
    assert len(salida) == 5
    assert salida[0]["id"] == f"f{R.CANDIDATOS - 1}"  # llegó reordenado, no crudo


def test_nunca_pide_menos_que_los_k_pedidos(indice, monkeypatch):
    """Si alguien pide más resultados que la ventana, manda el que pide: la
    ventana es un mínimo para reordenar, no un tope de la búsqueda."""
    monkeypatch.setattr(R, "activo", lambda: True)
    monkeypatch.setattr(R, "reordenar", lambda consulta, resultados, k=None: resultados[:k])

    indice.buscar("tutela", k=R.CANDIDATOS + 10)
    assert indice.pedidos == [(R.CANDIDATOS + 10, None)]


def test_el_filtro_de_fuentes_sobrevive_al_reordenado(indice, monkeypatch):
    monkeypatch.setattr(R, "activo", lambda: True)
    monkeypatch.setattr(R, "reordenar", lambda consulta, resultados, k=None: resultados[:k])

    indice.buscar("tutela", k=3, fuentes=["sic"])
    assert indice.pedidos == [(R.CANDIDATOS, ["sic"])]


def test_si_el_reranker_no_carga_la_busqueda_sigue_funcionando(indice, monkeypatch):
    """El caso del usuario sin el modelo descargado: una mejora opcional no
    puede convertir una búsqueda que funciona en un error."""
    monkeypatch.setattr(R, "activo", lambda: True)
    monkeypatch.setattr(R, "cargar_reranker", lambda: None)  # reordenar() devuelve el orden original

    salida = indice.buscar("tutela", k=4)
    assert [r["id"] for r in salida] == ["f0", "f1", "f2", "f3"]


def test_el_cliente_remoto_no_reordena_por_su_cuenta():
    """El .exe consulta por HTTP y no lleva la pila de ML: si el cliente remoto
    intentara reordenar, o pesaría 2 GB más o se caería en el equipo del
    usuario. Quien decide allí es el servidor."""
    fuente = (RAIZ / "index" / "cliente_remoto.py").read_text(encoding="utf-8")
    assert "reordenar" not in fuente
