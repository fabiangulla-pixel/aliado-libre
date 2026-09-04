"""Tests del servidor del índice. Nunca cargan el índice real (~11GB entre
Chroma y FTS5) ni importan index.buscar: se inyecta un doble en
servidor_indice.server._indice."""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import servidor_indice.server as srv
from servidor_indice.server import Handler

# Un fragmento con exactamente la forma que devuelve IndiceBusqueda.buscar():
# id + puntaje + texto + los metadatos del corpus aplanados en el mismo dict.
FRAGMENTO = {
    "id": "decreto-1083-2015::c17",
    "puntaje": 0.0412,
    "texto": "El empleado de carrera administrativa tiene derecho a...",
    "titulo_documento": "Decreto 1083 de 2015",
    "identificador_documento": "Decreto 1083 de 2015",
    "fuente": "Función Pública",
    "url_original": "https://www.funcionpublica.gov.co/decreto-1083-2015",
}


class IndiceFalso:
    def __init__(self, resultados=None, excepcion=None):
        self.resultados = [FRAGMENTO] if resultados is None else resultados
        self.excepcion = excepcion
        self.llamadas = []
        self._total = 718388

    def buscar(self, consulta, k=8):
        self.llamadas.append((consulta, k))
        if self.excepcion is not None:
            raise self.excepcion
        return self.resultados


@pytest.fixture()
def indice(monkeypatch):
    doble = IndiceFalso()
    monkeypatch.setattr(srv, "_indice", doble)
    monkeypatch.setattr(srv, "_total_fragmentos", doble._total)
    monkeypatch.setattr(srv, "_segundos_carga", 42.5)
    return doble


@pytest.fixture()
def base(indice):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture(autouse=True)
def sin_token(monkeypatch):
    """Por defecto los tests corren con el servidor abierto; los de auth
    definen la variable explícitamente."""
    monkeypatch.delenv("ALIADO_INDICE_TOKEN", raising=False)


def _post(base, ruta, cuerpo, token=None, crudo=None):
    datos = crudo if crudo is not None else json.dumps(cuerpo).encode("utf-8")
    peticion = urllib.request.Request(base + ruta, data=datos, method="POST")
    peticion.add_header("Content-Type", "application/json")
    if token:
        peticion.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(peticion, timeout=5)


# -- /salud ---------------------------------------------------------------


def test_salud_reporta_fragmentos_y_tiempo_de_carga(base):
    respuesta = urllib.request.urlopen(base + "/salud", timeout=5)
    datos = json.loads(respuesta.read())
    assert respuesta.status == 200
    assert datos["estado"] == "listo"
    assert datos["fragmentos"] == 718388
    assert datos["segundos_carga"] == 42.5
    assert datos["autenticado"] is False


def test_salud_sin_indice_cargado_lo_dice(base, monkeypatch):
    monkeypatch.setattr(srv, "_indice", None)
    datos = json.loads(urllib.request.urlopen(base + "/salud", timeout=5).read())
    assert datos["estado"] == "sin_indice"


# -- /buscar: esquema -----------------------------------------------------


def test_buscar_devuelve_el_mismo_esquema_de_fragmentos(base, indice):
    datos = json.loads(_post(base, "/buscar", {"consulta": "carrera administrativa", "n": 3}).read())
    assert datos["consulta"] == "carrera administrativa"
    assert datos["n"] == 3
    assert datos["resultados"] == [FRAGMENTO]
    # el servidor no reordena ni renombra claves: reemplazo transparente
    assert set(datos["resultados"][0]) == set(FRAGMENTO)
    assert indice.llamadas == [("carrera administrativa", 3)]


def test_buscar_usa_n_por_defecto_si_no_se_manda(base, indice):
    _post(base, "/buscar", {"consulta": "pensión"})
    assert indice.llamadas == [("pensión", srv.N_DEFECTO)]


def test_buscar_topa_n_en_el_maximo(base, indice):
    _post(base, "/buscar", {"consulta": "tutela", "n": 10_000})
    assert indice.llamadas == [("tutela", srv.N_MAXIMO)]


def test_buscar_acepta_acentos_y_devuelve_utf8(base, indice):
    indice.resultados = [{**FRAGMENTO, "texto": "acción de tutela y garantías mínimas"}]
    respuesta = _post(base, "/buscar", {"consulta": "acción de tutela"})
    assert "charset=utf-8" in respuesta.headers["Content-Type"]
    datos = json.loads(respuesta.read().decode("utf-8"))
    assert "garantías mínimas" in datos["resultados"][0]["texto"]


def test_buscar_sin_resultados_devuelve_lista_vacia(base, indice):
    indice.resultados = []
    datos = json.loads(_post(base, "/buscar", {"consulta": "xyz"}).read())
    assert datos["resultados"] == []


# -- /buscar: entradas inválidas ------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"consulta": ""},
        {"consulta": "   "},
        {"consulta": 42},
        {"consulta": None},
        {"consulta": "ok", "n": 0},
        {"consulta": "ok", "n": -3},
        {"consulta": "ok", "n": "cinco"},
        {"consulta": "ok", "n": True},
    ],
)
def test_buscar_rechaza_cuerpos_invalidos_con_400(base, cuerpo):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", cuerpo)
    assert exc.value.code == 400


def test_buscar_con_json_malformado_da_400(base):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", None, crudo=b"{esto no es json,,,")
    assert exc.value.code == 400
    assert "JSON" in json.loads(exc.value.read())["error"]


def test_buscar_con_json_que_no_es_objeto_da_400(base):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", None, crudo=b'["consulta"]')
    assert exc.value.code == 400


def test_buscar_con_cuerpo_enorme_da_413(base):
    enorme = json.dumps({"consulta": "a" * (srv.MAX_CUERPO + 100)}).encode("utf-8")
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", None, crudo=enorme)
    assert exc.value.code == 413


def test_fallo_del_indice_da_500_y_no_filtra_traza(base, indice):
    indice.excepcion = ValueError("chroma corrupto")
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", {"consulta": "algo"})
    assert exc.value.code == 500
    assert "chroma corrupto" in json.loads(exc.value.read())["error"]


def test_buscar_sin_indice_cargado_da_503(base, monkeypatch):
    monkeypatch.setattr(srv, "_indice", None)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", {"consulta": "algo"})
    assert exc.value.code == 503


# -- métodos y rutas ------------------------------------------------------


def test_get_a_buscar_da_405_con_allow(base):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + "/buscar", timeout=5)
    assert exc.value.code == 405
    assert exc.value.headers["Allow"] == "POST"


def test_post_a_salud_da_405(base):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/salud", {})
    assert exc.value.code == 405
    assert exc.value.headers["Allow"] == "GET"


@pytest.mark.parametrize("ruta", ["/", "/admin", "/index/chroma_db", "/../servidor_indice/server.py"])
def test_rutas_inesperadas_dan_404(base, ruta):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + ruta, timeout=5)
    assert exc.value.code == 404


def test_post_a_ruta_inesperada_da_404(base):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/otra", {"consulta": "x"})
    assert exc.value.code == 404


def test_barra_final_no_crea_ruta_distinta(base, indice):
    datos = json.loads(_post(base, "/buscar/", {"consulta": "x"}).read())
    assert datos["resultados"] == [FRAGMENTO]


# -- autenticación --------------------------------------------------------


@pytest.fixture()
def con_token(monkeypatch):
    monkeypatch.setenv("ALIADO_INDICE_TOKEN", "secreto-compartido")
    return "secreto-compartido"


def test_buscar_sin_token_da_401_cuando_hay_token_configurado(base, con_token):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", {"consulta": "algo"})
    assert exc.value.code == 401


def test_salud_sin_token_da_401_cuando_hay_token_configurado(base, con_token):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + "/salud", timeout=5)
    assert exc.value.code == 401


def test_token_incorrecto_da_401(base, con_token):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/buscar", {"consulta": "algo"}, token="otro")
    assert exc.value.code == 401


def test_esquema_no_bearer_da_401(base, con_token):
    peticion = urllib.request.Request(base + "/salud")
    peticion.add_header("Authorization", f"Basic {con_token}")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(peticion, timeout=5)
    assert exc.value.code == 401


def test_token_correcto_pasa(base, con_token, indice):
    datos = json.loads(_post(base, "/buscar", {"consulta": "algo"}, token=con_token).read())
    assert datos["resultados"] == [FRAGMENTO]


def test_salud_reporta_que_esta_autenticado(base, con_token):
    peticion = urllib.request.Request(base + "/salud")
    peticion.add_header("Authorization", f"Bearer {con_token}")
    datos = json.loads(urllib.request.urlopen(peticion, timeout=5).read())
    assert datos["autenticado"] is True


def test_token_vacio_en_la_variable_equivale_a_abierto(base, monkeypatch):
    monkeypatch.setenv("ALIADO_INDICE_TOKEN", "   ")
    assert srv.token_configurado() is None
    assert urllib.request.urlopen(base + "/salud", timeout=5).status == 200
