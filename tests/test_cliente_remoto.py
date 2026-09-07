"""Tests del cliente del índice remoto. Sin red real: se sustituye
urllib.request.urlopen. Tampoco se importa index.buscar (torch/chroma)."""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from index.cliente_remoto import ErrorIndiceRemoto, IndiceRemoto

FRAGMENTO = {
    "id": "ley-1437-2011::c3",
    "puntaje": 0.0333,
    "texto": "Toda persona podrá acudir ante las autoridades...",
    "titulo_documento": "Ley 1437 de 2011",
    "identificador_documento": "Ley 1437 de 2011",
    "fuente": "Secretaría del Senado",
    "url_original": "https://www.secretariasenado.gov.co/ley-1437-2011",
}


class RespuestaFalsa(io.BytesIO):
    """Lo mínimo que urlopen() devuelve y que el cliente usa: read() y
    el protocolo de gestor de contexto."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _respuesta(datos):
    crudo = datos if isinstance(datos, bytes) else json.dumps(datos).encode("utf-8")
    return RespuestaFalsa(crudo)


def _error_http(codigo, cuerpo=None):
    crudo = json.dumps(cuerpo or {}).encode("utf-8")
    return urllib.error.HTTPError("http://x/buscar", codigo, "err", {}, io.BytesIO(crudo))


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    monkeypatch.delenv("ALIADO_INDICE_URL", raising=False)
    monkeypatch.delenv("ALIADO_INDICE_TOKEN", raising=False)


# -- construcción ---------------------------------------------------------


def test_sin_url_falla_con_mensaje_claro_en_espanol():
    with pytest.raises(ErrorIndiceRemoto) as exc:
        IndiceRemoto()
    assert "ALIADO_INDICE_URL" in str(exc.value)


def test_toma_url_y_token_del_entorno(monkeypatch):
    monkeypatch.setenv("ALIADO_INDICE_URL", "https://indice.example.com/")
    monkeypatch.setenv("ALIADO_INDICE_TOKEN", "abc123")
    cliente = IndiceRemoto()
    assert cliente.url == "https://indice.example.com"  # sin barra final
    assert cliente.token == "abc123"


# -- éxito ----------------------------------------------------------------


def test_buscar_devuelve_los_fragmentos_tal_cual():
    cliente = IndiceRemoto("http://indice.local")
    with patch("urllib.request.urlopen", return_value=_respuesta({"resultados": [FRAGMENTO]})):
        assert cliente.buscar("acción de tutela", k=3) == [FRAGMENTO]


def test_buscar_envia_post_json_con_consulta_n_y_token():
    cliente = IndiceRemoto("http://indice.local", token="secreto")
    with patch("urllib.request.urlopen", return_value=_respuesta({"resultados": []})) as fake:
        cliente.buscar("pensión de invalidez", k=5)
    peticion = fake.call_args[0][0]
    assert peticion.full_url == "http://indice.local/buscar"
    assert peticion.get_method() == "POST"
    assert peticion.get_header("Authorization") == "Bearer secreto"
    assert json.loads(peticion.data.decode("utf-8")) == {"consulta": "pensión de invalidez", "n": 5}


def test_sin_token_no_manda_cabecera_de_autorizacion():
    cliente = IndiceRemoto("http://indice.local")
    with patch("urllib.request.urlopen", return_value=_respuesta({"resultados": []})) as fake:
        cliente.buscar("x")
    assert fake.call_args[0][0].get_header("Authorization") is None


def test_consulta_vacia_no_toca_la_red():
    cliente = IndiceRemoto("http://indice.local")
    with patch("urllib.request.urlopen") as fake:
        assert cliente.buscar("   ") == []
    fake.assert_not_called()


def test_salud_hace_get_sin_cuerpo():
    cliente = IndiceRemoto("http://indice.local")
    with patch("urllib.request.urlopen", return_value=_respuesta({"estado": "listo"})) as fake:
        assert cliente.salud()["estado"] == "listo"
    peticion = fake.call_args[0][0]
    assert peticion.get_method() == "GET"
    assert peticion.full_url == "http://indice.local/salud"


def test_interfaz_compatible_con_indice_local():
    """El resto del código llama buscar(consulta, k=...) sin saber cuál usa."""
    import inspect

    firma = inspect.signature(IndiceRemoto.buscar)
    assert list(firma.parameters) == ["self", "consulta", "k", "fuentes"]

    # La firma tiene que coincidir con la del indice local, o cambiar de modo
    # (local <-> nube) alteraria el comportamiento en silencio. Se compara sin
    # importar index.buscar, que arrastraria torch a esta suite.
    from pathlib import Path as _P

    fuente = (_P(__file__).resolve().parent.parent / "index" / "buscar.py").read_text(encoding="utf-8")
    assert "def buscar(self, consulta: str, k: int = 8, fuentes: list[str] | None = None)" in fuente
    assert firma.parameters["k"].default == 8


# -- errores de red -------------------------------------------------------


def test_timeout_da_mensaje_claro_en_espanol():
    cliente = IndiceRemoto("http://indice.local", espera=7)
    fallo = urllib.error.URLError(TimeoutError("timed out"))
    with patch("urllib.request.urlopen", side_effect=fallo), pytest.raises(ErrorIndiceRemoto) as exc:
        cliente.buscar("algo")
    mensaje = str(exc.value)
    assert "no respondió en 7 segundos" in mensaje
    assert "reintenta" in mensaje.lower()


def test_timeout_desnudo_tambien_se_traduce():
    cliente = IndiceRemoto("http://indice.local", espera=30)
    with (
        patch("urllib.request.urlopen", side_effect=TimeoutError()),
        pytest.raises(ErrorIndiceRemoto) as exc,
    ):
        cliente.buscar("algo")
    assert "no respondió en 30 segundos" in str(exc.value)


def test_sin_conexion_da_mensaje_claro():
    cliente = IndiceRemoto("http://indice.local")
    fallo = urllib.error.URLError(ConnectionRefusedError("conexión rechazada"))
    with patch("urllib.request.urlopen", side_effect=fallo), pytest.raises(ErrorIndiceRemoto) as exc:
        cliente.buscar("algo")
    assert "No se pudo conectar" in str(exc.value)
    assert "http://indice.local" in str(exc.value)


# -- errores HTTP ---------------------------------------------------------


def test_401_habla_del_token():
    cliente = IndiceRemoto("http://indice.local")
    with (
        patch("urllib.request.urlopen", side_effect=_error_http(401, {"error": "Token ausente"})),
        pytest.raises(ErrorIndiceRemoto) as exc,
    ):
        cliente.buscar("algo")
    assert "401" in str(exc.value)
    assert "ALIADO_INDICE_TOKEN" in str(exc.value)
    assert "Token ausente" in str(exc.value)


def test_404_habla_de_la_url():
    cliente = IndiceRemoto("http://indice.local")
    with (
        patch("urllib.request.urlopen", side_effect=_error_http(404)),
        pytest.raises(ErrorIndiceRemoto) as exc,
    ):
        cliente.buscar("algo")
    assert "Verifica la URL" in str(exc.value)


def test_503_sugiere_reintentar():
    cliente = IndiceRemoto("http://indice.local")
    with (
        patch("urllib.request.urlopen", side_effect=_error_http(503)),
        pytest.raises(ErrorIndiceRemoto) as exc,
    ):
        cliente.buscar("algo")
    assert "Reintenta" in str(exc.value)


def test_500_se_reporta_como_fallo_del_servidor():
    cliente = IndiceRemoto("http://indice.local")
    with (
        patch("urllib.request.urlopen", side_effect=_error_http(500, {"error": "chroma corrupto"})),
        pytest.raises(ErrorIndiceRemoto) as exc,
    ):
        cliente.buscar("algo")
    assert "falló (500)" in str(exc.value)
    assert "chroma corrupto" in str(exc.value)


def test_cuerpo_de_error_ilegible_no_tapa_el_codigo_http():
    cliente = IndiceRemoto("http://indice.local")
    fallo = urllib.error.HTTPError("http://x", 502, "bad gw", {}, io.BytesIO(b"<html>nginx</html>"))
    with patch("urllib.request.urlopen", side_effect=fallo), pytest.raises(ErrorIndiceRemoto) as exc:
        cliente.buscar("algo")
    assert "502" in str(exc.value)


# -- respuestas mal formadas ----------------------------------------------


def test_respuesta_que_no_es_json_da_error_claro():
    cliente = IndiceRemoto("http://indice.local")
    with (
        patch("urllib.request.urlopen", return_value=_respuesta(b"<html>proxy</html>")),
        pytest.raises(ErrorIndiceRemoto) as exc,
    ):
        cliente.buscar("algo")
    assert "no es JSON válido" in str(exc.value)


def test_respuesta_sin_lista_resultados_da_error_claro():
    cliente = IndiceRemoto("http://indice.local")
    with (
        patch("urllib.request.urlopen", return_value=_respuesta({"ok": True})),
        pytest.raises(ErrorIndiceRemoto) as exc,
    ):
        cliente.buscar("algo")
    assert "'resultados'" in str(exc.value)


# -- reintentos -----------------------------------------------------------
#
# Un servidor en plan barato se suspende por inactividad: el primer usuario
# tras la pausa se topa con un 503 o un timeout mientras carga los 11GB de
# índice. Eso cura solo esperando, así que se reintenta; un 401 no.


def test_503_se_reintenta_y_la_segunda_vez_funciona():
    respuestas = [_error_http(503), _respuesta({"resultados": [FRAGMENTO]})]

    def falso(*args, **kwargs):
        item = respuestas.pop(0)
        if isinstance(item, urllib.error.HTTPError):
            raise item
        return item

    with patch("urllib.request.urlopen", side_effect=falso), patch("time.sleep"):
        cliente = IndiceRemoto("http://x", reintentos=2)
        assert cliente.buscar("tutela") == [FRAGMENTO]
    assert respuestas == []


def test_timeout_se_reintenta():
    intentos = []

    def falso(*args, **kwargs):
        intentos.append(1)
        if len(intentos) < 3:
            raise TimeoutError
        return _respuesta({"resultados": []})

    with patch("urllib.request.urlopen", side_effect=falso), patch("time.sleep"):
        assert IndiceRemoto("http://x", reintentos=2).buscar("tutela") == []
    assert len(intentos) == 3


def test_401_no_se_reintenta_nunca():
    intentos = []

    def falso(*args, **kwargs):
        intentos.append(1)
        raise _error_http(401)

    with patch("urllib.request.urlopen", side_effect=falso), patch("time.sleep"):
        with pytest.raises(ErrorIndiceRemoto):
            IndiceRemoto("http://x", reintentos=3).buscar("tutela")
    assert len(intentos) == 1, "un token malo no mejora por insistir"


def test_agotados_los_reintentos_se_reporta_el_ultimo_error():
    def falso(*args, **kwargs):
        raise _error_http(503)

    with patch("urllib.request.urlopen", side_effect=falso), patch("time.sleep"):
        with pytest.raises(ErrorIndiceRemoto) as exc:
            IndiceRemoto("http://x", reintentos=1).buscar("tutela")
    assert "503" in str(exc.value)


def test_reintentos_cero_falla_a_la_primera():
    intentos = []

    def falso(*args, **kwargs):
        intentos.append(1)
        raise _error_http(503)

    with patch("urllib.request.urlopen", side_effect=falso), patch("time.sleep"):
        with pytest.raises(ErrorIndiceRemoto):
            IndiceRemoto("http://x", reintentos=0).buscar("tutela")
    assert len(intentos) == 1


def test_la_espera_entre_intentos_crece():
    esperas = []

    def falso(*args, **kwargs):
        raise _error_http(503)

    with (
        patch("urllib.request.urlopen", side_effect=falso),
        patch("time.sleep", side_effect=esperas.append),
    ):
        with pytest.raises(ErrorIndiceRemoto):
            IndiceRemoto("http://x", reintentos=3).buscar("tutela")
    assert esperas == [2.0, 4.0, 8.0]
