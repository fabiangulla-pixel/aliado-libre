import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

import gui.server as servidor_modulo
from gui.server import Handler


@pytest.fixture()
def servidor():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    puerto = srv.server_address[1]
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{puerto}"
    srv.shutdown()


def test_sirve_index_html(servidor):
    r = urllib.request.urlopen(servidor + "/")
    assert r.status == 200
    assert b"Aliado" in r.read()


def test_api_estado_no_carga_indice_por_defecto(servidor):
    r = urllib.request.urlopen(servidor + "/api/estado")
    datos = json.loads(r.read())
    assert datos["cargado"] is False


def test_api_buscar_sin_consulta_da_400(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(servidor + "/api/buscar")
    assert exc_info.value.code == 400


def test_ruta_desconocida_da_404(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(servidor + "/no/existe.html")
    assert exc_info.value.code == 404


def test_no_permite_escapar_del_directorio_estatico(servidor):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(servidor + "/../server.py")
    assert exc_info.value.code == 404


def test_buscar_sin_conversacional_no_incluye_respuesta(servidor):
    with patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_falso()):
        r = urllib.request.urlopen(servidor + "/api/buscar?q=algo")
        datos = json.loads(r.read())
    assert "respuesta" not in datos
    assert datos["resultados"] == [{"texto": "x"}]


def test_buscar_con_conversacional_incluye_respuesta(servidor):
    with (
        patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_falso()),
        patch("index.responder.responder", return_value="Respuesta redactada."),
    ):
        r = urllib.request.urlopen(servidor + "/api/buscar?q=algo&conversacional=1")
        datos = json.loads(r.read())
    assert datos["respuesta"] == "Respuesta redactada."


def test_buscar_con_conversacional_degrada_si_ollama_falla(servidor):
    with (
        patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_falso()),
        patch("index.responder.responder", side_effect=RuntimeError("Ollama caído")),
    ):
        r = urllib.request.urlopen(servidor + "/api/buscar?q=algo&conversacional=1")
        datos = json.loads(r.read())
    assert datos["respuesta"] is None
    assert "Ollama caído" in datos["aviso_respuesta"]
    assert datos["resultados"] == [{"texto": "x"}]  # los resultados crudos igual llegan


def _indice_falso():
    class IndiceFalso:
        def buscar(self, consulta, k):
            return [{"texto": "x"}]

    return IndiceFalso()


def test_no_permite_escapar_con_ruta_urlencodeada(servidor):
    # path traversal real: un cliente HTTP no normaliza "%2e%2e" antes de
    # enviarlo, a diferencia de "../" que muchos sí colapsan del lado cliente
    conn = http.client.HTTPConnection("127.0.0.1", int(servidor.rsplit(":", 1)[1]))
    conn.request("GET", "/%2e%2e/server.py")
    assert conn.getresponse().status == 404
