"""Búsqueda asistida por LLM: el orden lo pone el modelo y un fallo nunca rompe la búsqueda."""

import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from index import busqueda_asistida as ba


class _Bloque:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _ClienteFalso:
    """Primera llamada: reformulaciones. Segunda: los números elegidos."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []
        self.messages = self

    def create(self, **kw):
        self.llamadas.append(kw)
        return SimpleNamespace(
            content=[_Bloque(self._respuestas.pop(0))],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            stop_reason="end_turn",
        )


class _ColeccionFalsa:
    def get(self, ids, include):
        return {
            "ids": ids,
            "documents": [f"texto de {i}" for i in ids],
            "metadatas": [{"titulo_documento": i.split("::")[0]} for i in ids],
        }


class _IndiceFalso:
    _coleccion = _ColeccionFalsa()

    def __init__(self):
        self.consultas = []

    def listas_candidatos(self, consulta, n):
        self.consultas.append(consulta)
        return [["a::f0", "b::f0", "c::f0"], ["b::f1", "d::f0"]]


def test_fusion_un_fragmento_por_documento():
    orden = ba.fusionar([["a::f0", "a::f1", "b::f0"], ["b::f1"]])
    assert ba.un_fragmento_por_documento(orden, 10) == ["a::f0", "b::f0"]


def test_interpretar_ignora_repetidos_y_fuera_de_rango():
    assert ba.interpretar("3, 3, 99, 1, x 2", 5) == [3, 1, 2]


def test_el_orden_lo_pone_el_modelo_y_busca_las_reformulaciones():
    cliente = _ClienteFalso(["reformulacion uno\nreformulacion dos\nreformulacion tres", "3, 1"])
    indice = _IndiceFalso()
    with patch("anthropic.Anthropic", return_value=cliente):
        r = ba.buscar_asistida(indice, "me echaron", k=3, clave="x")
    assert indice.consultas == ["me echaron", "reformulacion uno", "reformulacion dos", "reformulacion tres"]
    pool = ba.un_fragmento_por_documento(
        ba.fusionar([["a::f0", "b::f0", "c::f0"], ["b::f1", "d::f0"]] * 4), 60
    )
    assert [x["id"] for x in r.resultados][:2] == [pool[2], pool[0]]
    assert len(r.resultados) == 3
    assert r.usd > 0
    # puntaje decreciente: quien ordene por puntaje respeta el orden del modelo
    puntajes = [x["puntaje"] for x in r.resultados]
    assert puntajes == sorted(puntajes, reverse=True)


def test_haiku_no_lleva_thinking_y_sonnet_si():
    for nombre, lleva in (("claude-haiku-4-5", False), ("claude-sonnet-5", True)):
        cliente = _ClienteFalso(["ok"])
        ba._llamar(cliente, nombre, "s", "t")
        assert ("thinking" in cliente.llamadas[0]) is lleva


def test_rechazo_del_modelo_es_un_error():
    cliente = _ClienteFalso(["x"])
    cliente.create = lambda **kw: SimpleNamespace(content=[], usage=None, stop_reason="refusal")
    with pytest.raises(RuntimeError):
        ba._llamar(cliente, "claude-sonnet-5", "s", "t")


# --- servidor -----------------------------------------------------------------


@pytest.fixture()
def servidor():
    from gui.server import Handler

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


class _IndiceServidor(_IndiceFalso):
    def buscar(self, consulta, k=8, fuentes=None):
        return [{"id": "z::f0", "puntaje": 0.05, "texto": "normal", "titulo_documento": "Z"}]


def _buscar(servidor, monkeypatch, asistida_lanza=False, clave="x", activa="1"):
    import gui.server as srv

    monkeypatch.setenv("ALIADO_BUSQUEDA_ASISTIDA", activa)

    def falsa(indice, consulta, k, clave):
        if asistida_lanza:
            raise ConnectionError("sin red")
        return ba.ResultadoAsistido([{"id": "a::f0", "puntaje": 1.0, "texto": "asistida"}], 0.03)

    with (
        patch.object(srv, "_obtener_indice", return_value=_IndiceServidor()),
        patch.object(ba, "buscar_asistida", side_effect=falsa),
        patch("finetune.clave_api.leer_clave", return_value=clave),
    ):
        return json.loads(urllib.request.urlopen(servidor + "/api/buscar?q=algo").read())


def test_servidor_usa_la_asistida_si_esta_encendida(servidor, monkeypatch):
    datos = _buscar(servidor, monkeypatch)
    assert datos["busqueda_asistida"] is True
    assert datos["resultados"][0]["id"] == "a::f0"


def test_servidor_degrada_a_la_normal_si_falla(servidor, monkeypatch):
    datos = _buscar(servidor, monkeypatch, asistida_lanza=True)
    assert datos["busqueda_asistida"] is False
    assert datos["resultados"][0]["id"] == "z::f0"


def test_servidor_sin_clave_no_la_usa(servidor, monkeypatch):
    datos = _buscar(servidor, monkeypatch, clave="")
    assert datos["busqueda_asistida"] is False


def test_servidor_apagada_no_la_usa(servidor, monkeypatch):
    datos = _buscar(servidor, monkeypatch, activa="0")
    assert datos["busqueda_asistida"] is False
