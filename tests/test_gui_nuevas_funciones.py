"""Endpoints del 27-nov-2026: escrito, documento, seguimiento, citas ubicadas,
relaciones de la Corte Constitucional y cupo semanal de las claves."""

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

import gui.server as servidor_modulo
from gui import publico
from gui.server import Handler
from index.proveedores import RespuestaProveedor
from servidor_indice import cuotas

TEXTO = "La licencia de conducción tendrá una vigencia de diez años para vehículos particulares."
RESPUESTA = "Hola. Revisa la Ley 769 de 2002: «La licencia de conducción tendrá una vigencia de diez años»."


class _Indice:
    def __init__(self):
        self.consultas = []

    def buscar(self, consulta, k, fuentes=None):
        self.consultas.append(consulta)
        return [
            {
                "id": "ley::frag0",
                "documento_id": "ley",
                "texto": TEXTO,
                "puntaje": 0.09,
                "titulo_documento": "Ley 769 de 2002",
            }
        ]


@pytest.fixture()
def web(monkeypatch, tmp_path):
    monkeypatch.delenv("ALIADO_PUBLICO", raising=False)
    publico.reiniciar()
    indice = _Indice()
    monkeypatch.setattr(servidor_modulo, "_obtener_indice", lambda: indice)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{srv.server_address[1]}", indice
    srv.shutdown()
    srv.server_close()
    publico.reiniciar()


def _get(url):
    try:
        r = urllib.request.urlopen(url, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(url, datos):
    req = urllib.request.Request(
        url, data=json.dumps(datos).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_estado_anuncia_las_capacidades_nuevas(web):
    url, _ = web
    _, d = _get(url + "/api/estado")
    assert {p["clave"] for p in d["escritos"]} == {"peticion", "servicios", "consumidor", "tutela"}
    assert "relaciones_constitucional" in d and "documento_servidor" in d


def test_escrito_por_post_y_error_legible(web):
    url, _ = web
    c, d = _post(
        url + "/api/escrito",
        {"tipo": "peticion", "hechos": "Pedí una copia de mi historia clínica y no me la dan."},
    )
    assert c == 200 and "DERECHO DE PETICIÓN" in d["texto"]
    c, d = _post(url + "/api/escrito", {"tipo": "inventado", "hechos": "x" * 30})
    assert c == 400 and "desconocido" in d["error"]


def test_seguimiento_busca_con_las_preguntas_anteriores_y_las_devuelve(web):
    url, indice = web
    c, d = _get(
        url
        + "/api/buscar?q="
        + urllib.parse.quote("¿y para motos?")
        + "&antes="
        + urllib.parse.quote("cuánto dura la licencia")
    )
    assert c == 200
    assert indice.consultas[-1] == "cuánto dura la licencia ¿y para motos?"
    assert d["seguimiento_de"] == ["cuánto dura la licencia"]
    _get(url + "/api/buscar?q=licencia")
    assert indice.consultas[-1] == "licencia"  # sin hilo, la consulta va sola


def test_seguimiento_le_dice_a_la_redaccion_de_que_se_venia_hablando(web):
    url, _ = web
    with patch("index.responder.responder", return_value=RESPUESTA) as resp:
        _, d = _get(url + "/api/buscar?q=motos&conversacional=1&antes=licencia")
    pregunta = resp.call_args[0][0]
    assert pregunta.startswith("motos") and "«licencia»" in pregunta
    # y la cita de la respuesta viene ubicada en su fuente
    (cita,) = d["citas_ubicadas"]
    u = cita["ubicaciones"][0]
    assert u["id"] == "ley::frag0" and TEXTO[u["inicio"] : u["fin"]].startswith("La licencia de conducción")


def test_documento_estima_sin_llamar_y_explica_con_la_clave_de_la_persona(web):
    url, indice = web
    carta = "Le cobramos $ 250.000 por reconexión del servicio de energía. Plazo: 5 días. C.C. 52.345.678"
    with patch("index.proveedores._claude") as llamada:
        c, d = _post(url + "/api/documento", {"texto": carta, "proveedor": "claude", "solo_estimar": True})
        assert c == 200 and d["estimado"]["usd"] > 0 and d["documento"]["enmascarado"]["documentos"] == 1
        llamada.assert_not_called()

        llamada.return_value = RespuestaProveedor(
            json.dumps(
                {
                    "tipo": "Cobro",
                    "explicacion": "Te cobran $ 250.000 por reconectar la energía y tienes 5 días.",
                    "puntos_clave": [],
                    "consultas": ["reconexión servicio público cobro"],
                }
            ),
            None,
            "claude",
            "claude-haiku-4-5",
        )
        c, d = _post(
            url + "/api/documento", {"texto": carta, "proveedor": "claude", "clave": "sk-ant-prueba-123456"}
        )
    assert c == 200 and d["anclada"] is True and d["resultados"][0]["id"] == "ley::frag0"
    assert indice.consultas[-1] == "reconexión servicio público cobro"
    # lo que viajó a la IA ya iba sin la cédula
    assert "52.345.678" not in llamada.call_args[0][0]


def test_documento_sin_clave_ni_servidor_lo_dice(web, monkeypatch):
    url, _ = web
    monkeypatch.setattr(Handler, "_hay_clave_servidor", staticmethod(lambda: False))
    c, d = _post(
        url + "/api/documento", {"texto": "Contrato de arrendamiento de vivienda urbana por un año."}
    )
    assert c == 503 and "clave" in d["error"]


def test_providencia_constitucional(web, monkeypatch, tmp_path):
    from index import relaciones_constitucional as rc

    url, _ = web
    raw = tmp_path / "cc.json"
    raw.write_text(
        json.dumps(
            [
                {"id": "corte_constitucional:1", "identificador": "T-760/08", "texto": "Salud."},
                {
                    "id": "corte_constitucional:2",
                    "identificador": "T-100/20",
                    "texto": "Ver sentencia T-760 de 2008.",
                },
            ]
        ),
        encoding="utf-8",
    )
    db = tmp_path / "rel.db"
    rc.construir([raw], db)
    monkeypatch.setattr(rc, "RELACIONES", db)
    c, d = _get(url + "/api/providencia?id=corte_constitucional:1")
    assert c == 200 and d["ficha"]["identificador"] == "T-760/08"
    assert d["relaciones"]["citada_por"][0]["identificador"] == "T-100/20"
    c, _ = _get(url + "/api/providencia?id=corte_constitucional:404")
    assert c == 404


def test_cupo_semanal_de_las_claves():
    clave = "al_prueba"
    planes = {cuotas.hash_clave(clave): cuotas.Plan("semanal", 2, "semana")}
    q = cuotas.Cuotas(claves=planes)
    lunes = datetime(2026, 11, 23, 15, tzinfo=UTC)  # lunes 23-nov, 10:00 en Colombia
    domingo = datetime(2026, 11, 30, 4, tzinfo=UTC)  # domingo 29-nov, 23:00 en Colombia
    otro_lunes = datetime(2026, 11, 30, 6, tzinfo=UTC)  # lunes 30-nov, 01:00 en Colombia
    assert q.consumir("ip", clave, lunes).permitido and q.consumir("ip", clave, lunes).permitido
    bloqueo = q.consumir("ip", clave, domingo)
    assert not bloqueo.permitido and "próximo lunes" in cuotas.mensaje_bloqueo(bloqueo)
    assert cuotas.segundos_hasta_renovar(bloqueo, domingo) == 3600
    assert q.consumir("ip", clave, otro_lunes).permitido
    assert cuotas._plan_desde_dict({"tope": 5, "periodo": "semana"}).periodo == "semana"


# --- 27-nov-2026 (tarde) ----------------------------------------------------------


def test_plazo_por_get(web):
    url, _ = web
    c, d = _get(url + "/api/plazo?desde=2026-11-27&dias=15")
    assert c == 200 and d["vence"] == "2026-12-21"
    c, d = _get(url + "/api/plazo?desde=ayer&dias=15")
    assert c == 400


def test_verificar_citas_por_post(web):
    url, _ = web
    c, d = _post(url + "/api/verificar_citas", {"texto": "Según la Ley 99999 de 2020."})
    assert (
        c == 200
        and d["resumen"]["total"] == 1
        and d["citas"][0]["estado"] in ("no_en_indice", "sin_catalogo")
    )
    c, _ = _post(url + "/api/verificar_citas", {"texto": "   "})
    assert c == 400


def test_liquidacion_apagada_y_encendida(web, monkeypatch):
    url, _ = web
    datos = {"fecha_ingreso": "2025-01-01", "fecha_retiro": "2025-12-31", "salario": 3000000}
    monkeypatch.delenv("ALIADO_LIQUIDACION", raising=False)
    c, _ = _post(url + "/api/liquidacion", datos)
    assert c == 404
    monkeypatch.setenv("ALIADO_LIQUIDACION", "1")
    c, d = _post(url + "/api/liquidacion", datos)
    assert c == 200 and d["total"] > 0


def test_pagos_y_whatsapp_apagados_responden_sin_error(web, monkeypatch):
    url, _ = web
    monkeypatch.delenv("ALIADO_PAGOS", raising=False)
    monkeypatch.delenv("ALIADO_WHATSAPP", raising=False)
    c, d = _get(url + "/api/pago/planes")
    assert c == 404 and "no están activos" in d["error"]
    try:
        urllib.request.urlopen(
            url + "/api/whatsapp?hub.mode=subscribe&hub.verify_token=x&hub.challenge=1", timeout=5
        )
        codigo = 200
    except urllib.error.HTTPError as e:
        codigo = e.code
    assert codigo == 403


def test_clave_de_membresia_invalida_se_rechaza_en_publico(web, monkeypatch):
    url, _ = web
    monkeypatch.setenv("ALIADO_PUBLICO", "1")
    publico.reiniciar()
    req = urllib.request.Request(url + "/api/buscar?q=licencia", headers={"X-Aliado-Clave": "al_inventada"})
    try:
        urllib.request.urlopen(req, timeout=5)
        codigo = 200
    except urllib.error.HTTPError as e:
        codigo, cuerpo = e.code, json.loads(e.read())
    assert codigo == 401 and cuerpo["clave_invalida"] is True
