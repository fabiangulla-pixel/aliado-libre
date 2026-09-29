"""Herramientas MCP: entradas acotadas y vigencia en la salida. Índice falso."""

import pytest

import index.vigencia as vig
import mcp_server.server as srv


class _IndiceFalso:
    def __init__(self):
        self.k_pedido = None

    def buscar(self, consulta, k=5):
        self.k_pedido = k
        return [
            {
                "id": "dian:tributario:decreto_0150_1997::frag11",
                "identificador_documento": "dian:tributario:decreto_0150_1997",
                "titulo_documento": "Decreto 150 de 1997",
                "fuente": "dian",
                "url_original": "https://example.org",
                "texto": "ARTÍCULO 9o. <Decreto INEXEQUIBLE> tarifa del 10%",
            }
        ]


@pytest.fixture
def indice(monkeypatch):
    falso = _IndiceFalso()
    monkeypatch.setattr(srv, "_obtener_indice", lambda: falso)
    monkeypatch.setattr(vig, "_tabla", {})
    return falso


def test_buscar_normativa_informa_vigencia(indice):
    salida = srv.buscar_normativa("tarifa retención exterior")
    assert "Vigencia: TODA LA NORMA: INEXEQUIBLE" in salida
    assert "<fragmento>" in salida


@pytest.mark.parametrize(("pedido", "esperado"), [(10_000, srv.MAX_RESULTADOS), (-3, 1), ("x", 5)])
def test_max_resultados_acotado(indice, pedido, esperado):
    srv.buscar_normativa("algo", max_resultados=pedido)
    assert indice.k_pedido == esperado


def test_consulta_vacia_no_busca(indice):
    assert srv.buscar_normativa("   ") == "Consulta vacía."
    assert indice.k_pedido is None


@pytest.mark.parametrize("malo", ["../../etc/passwd", "a" * 300, "x; DROP TABLE", ""])
def test_ids_invalidos_rechazados(malo):
    assert "inválido" in srv.verificar_vigencia(malo)
    assert "inválido" in srv.leer_fragmento(malo)


def test_verificar_vigencia_distingue_sin_nota_de_vigente(monkeypatch):
    monkeypatch.setattr(
        vig,
        "_tabla",
        {"dian:x:decreto_1_2000": {"estado": "derogada", "texto": "Decreto derogado", "por": "Ley 2"}},
    )
    assert "DEROGADA" in srv.verificar_vigencia("dian:x:decreto_1_2000")
    assert "No prueba que esté vigente" in srv.verificar_vigencia("dian:x:otra_1_2000")
