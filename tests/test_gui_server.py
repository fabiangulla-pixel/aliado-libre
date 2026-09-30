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
    assert datos["resultados"] == [{"texto": "x", "puntaje": 0.09}]


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
    assert datos["resultados"] == [{"texto": "x", "puntaje": 0.09}]  # los resultados crudos igual llegan


def _indice_falso(puntaje: float = 0.09):
    """Indice de mentira con un puntaje POR ENCIMA del umbral de abstencion.

    Antes devolvia un resultado sin puntaje, y daba igual porque la GUI no
    consultaba al enrutador. Desde el 12-sep-2026 si lo consulta, y un
    resultado sin puntaje es —con razon— un resultado sin respaldo. Para
    probar el camino en que la aplicacion SI responde hay que darle algo que
    de verdad se parezca a la consulta.
    """

    class IndiceFalso:
        def buscar(self, consulta, k, fuentes=None):
            return [{"texto": "x", "puntaje": puntaje}]

    return IndiceFalso()


def test_no_permite_escapar_con_ruta_urlencodeada(servidor):
    # path traversal real: un cliente HTTP no normaliza "%2e%2e" antes de
    # enviarlo, a diferencia de "../" que muchos sí colapsan del lado cliente
    conn = http.client.HTTPConnection("127.0.0.1", int(servidor.rsplit(":", 1)[1]))
    conn.request("GET", "/%2e%2e/server.py")
    assert conn.getresponse().status == 404


# -- la aplicacion dice cuando no tiene la respuesta ------------------------
#
# Regla 1 del proyecto: los huecos del indice se dicen, no se disimulan. La
# logica estaba escrita y calibrada en index/enrutador.py desde hacia dias, y
# la GUI no la llamaba: ante "puedo tener mi herencia antes de que mueran mis
# padres" el enrutador dictaminaba "ningun documento se acerca lo suficiente" y
# la pantalla mostraba un decreto de 1938 sobre la Caja de Auxilios de la
# Policia Nacional como si fuera la respuesta.


def test_sin_respaldo_la_busqueda_lo_dice(servidor):
    """Prueba negativa: con puntajes bajos la GUI tiene que avisar."""
    with patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_falso(0.001)):
        r = urllib.request.urlopen(servidor + "/api/buscar?q=algo")
        datos = json.loads(r.read())
    assert datos["hay_respaldo"] is False
    assert datos["aviso_cobertura"]
    # Los fragmentos se siguen mandando: pueden servir de pista, pero van
    # encabezados por el aviso, no presentados como respuesta.
    assert datos["resultados"]


def test_sin_respaldo_no_se_redacta_respuesta(servidor):
    """Redactar sobre fragmentos que no responden es inventar cobertura cara."""
    with (
        patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_falso(0.001)),
        patch("index.responder.responder", return_value="Respuesta inventada."),
    ):
        r = urllib.request.urlopen(servidor + "/api/buscar?q=algo&conversacional=1")
        datos = json.loads(r.read())
    assert datos["hay_respaldo"] is False
    assert datos["respuesta"] is None


def test_con_respaldo_si_responde(servidor):
    """La guarda tiene que dejar pasar lo bueno, o solo seria un apagon."""
    with patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_falso(0.09)):
        r = urllib.request.urlopen(servidor + "/api/buscar?q=algo")
        datos = json.loads(r.read())
    assert datos["hay_respaldo"] is True
    assert datos["aviso_cobertura"] is None


def test_estado_dice_si_el_modelo_local_existe(servidor):
    """La casilla de redactar en local no debe ofrecer lo que no esta."""
    r = urllib.request.urlopen(servidor + "/api/estado")
    datos = json.loads(r.read())
    assert "modelo_local" in datos
    assert isinstance(datos["modelo_local"], bool)


# -- coincidencia débil: se redacta, pero solo se muestra lo respaldado ------
# 29-sep-2026: el umbral mide si coinciden los dos motores, no si hay
# respuesta. En el piloto callaba en 48 consultas, 21 de ellas con una norma y
# citas literales verificadas.

TEXTO_NORMA = "La licencia de conducción tendrá una vigencia de diez años para vehículos particulares."


def _indice_debil():
    class IndiceFalso:
        def buscar(self, consulta, k, fuentes=None):
            return [
                {
                    "id": "ley::frag0",
                    "texto": TEXTO_NORMA,
                    "puntaje": 0.0167,
                    "titulo_documento": "Ley 769 de 2002",
                }
            ]

    return IndiceFalso()


def test_debil_con_cita_literal_se_muestra_marcada(servidor):
    respuesta = (
        "Hola. Revisa la Ley 769 de 2002, que dice: «La licencia de conducción tendrá una vigencia de "
        "diez años para vehículos particulares». Es decir, dura diez años."
    )
    with (
        patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_debil()),
        patch("index.responder.responder", return_value=respuesta),
    ):
        datos = json.loads(
            urllib.request.urlopen(servidor + "/api/buscar?q=licencia&conversacional=1").read()
        )
    assert datos["respaldo"] == "condicional"
    assert datos["respuesta"] == respuesta
    assert datos["respaldo_debil"] is True


def test_debil_con_cita_inventada_no_se_muestra(servidor):
    """Prueba negativa: la misma coincidencia débil con una cita que no está
    en el texto no llega a la persona."""
    respuesta = "Hola. La Ley 769 dice: «La licencia de conducción dura quince años en todos los casos»."
    with (
        patch.object(servidor_modulo, "_obtener_indice", return_value=_indice_debil()),
        patch("index.responder.responder", return_value=respuesta),
    ):
        datos = json.loads(
            urllib.request.urlopen(servidor + "/api/buscar?q=licencia&conversacional=1").read()
        )
    assert datos["respuesta"] is None
    assert "no aparecen literalmente" in datos["aviso_respuesta"]
    assert datos["resultados"]  # los fragmentos siguen como pista
