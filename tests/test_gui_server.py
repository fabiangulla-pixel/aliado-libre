import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

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


def test_no_permite_escapar_con_ruta_urlencodeada(servidor):
    # path traversal real: un cliente HTTP no normaliza "%2e%2e" antes de
    # enviarlo, a diferencia de "../" que muchos sí colapsan del lado cliente
    conn = http.client.HTTPConnection("127.0.0.1", int(servidor.rsplit(":", 1)[1]))
    conn.request("GET", "/%2e%2e/server.py")
    assert conn.getresponse().status == 404
