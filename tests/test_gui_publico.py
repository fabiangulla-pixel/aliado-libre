"""Modo público de la web (gui/publico.py): cuota, redacción limitada, túnel."""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

import gui.server as servidor_modulo
from gui import publico
from gui.server import Handler

TEXTO = "La licencia de conducción tendrá una vigencia de diez años para vehículos particulares."
RESPUESTA = (
    "Hola. Revisa la Ley 769 de 2002: «La licencia de conducción tendrá una vigencia de diez años "
    "para vehículos particulares». Es decir, dura diez años."
)


class _Indice:
    def buscar(self, consulta, k, fuentes=None):
        return [{"id": "ley::frag0", "texto": TEXTO, "puntaje": 0.09, "titulo_documento": "Ley 769 de 2002"}]


@pytest.fixture()
def web(monkeypatch, tmp_path):
    monkeypatch.setenv("ALIADO_PUBLICO", "1")
    monkeypatch.setenv("ALIADO_TOPE_APORTE", "1")
    monkeypatch.setenv("ALIADO_TOPE_DIARIO_IP", "3")
    monkeypatch.setenv("ALIADO_REDACCIONES_DIARIAS", "2")
    monkeypatch.delenv("ALIADO_CONFIAR_PROXY", raising=False)
    publico.reiniciar()
    monkeypatch.setattr(publico, "_presupuesto", publico.Presupuesto(0.01, tmp_path / "gasto.json"))
    monkeypatch.setattr(servidor_modulo, "_obtener_indice", lambda: _Indice())
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.05)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()
    publico.reiniciar()


def _get(url, cabeceras=None):
    req = urllib.request.Request(url, headers=cabeceras or {})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_estado_publico_da_nombre_y_no_ofrece_modelo_local(web):
    _, d = _get(web + "/api/estado")
    assert d["publico"] is True and d["modelo_local"] is False
    assert d["nombre"] == "Juris-consulta ColombIA"
    assert d["redacciones_diarias"] == 2


def test_cuota_de_busqueda_aporte_y_bloqueo(web):
    r = [_get(web + "/api/buscar?q=licencia") for _ in range(4)]
    assert [c for c, _ in r] == [200, 200, 200, 429]
    assert r[0][1]["aviso_aporte"] is None and "aporte" in r[1][1]["aviso_aporte"]
    assert "límite" in r[3][1]["error"]


def test_redaccion_con_cuota_propia_y_la_busqueda_sigue(web, monkeypatch):
    monkeypatch.setenv("ALIADO_TOPE_DIARIO_IP", "10")
    publico.reiniciar()
    with patch.object(publico, "redactar", return_value=(RESPUESTA, 0.001)):
        r = [_get(web + "/api/buscar?q=licencia&conversacional=1")[1] for _ in range(3)]
    assert r[0]["respuesta"] == RESPUESTA and r[1]["respuesta"] == RESPUESTA
    assert r[2]["respuesta"] is None and "respuestas redactadas gratis" in r[2]["aviso_respuesta"]
    assert r[2]["resultados"]  # la búsqueda con citas no se corta


def test_tope_de_gasto_mensual_pausa_la_redaccion(web, monkeypatch):
    with patch.object(publico, "redactar", return_value=(RESPUESTA, 0.02)):
        primera = _get(web + "/api/buscar?q=licencia&conversacional=1")[1]
        segunda = _get(web + "/api/buscar?q=licencia&conversacional=1")[1]
    assert primera["respuesta"] == RESPUESTA
    assert segunda["respuesta"] is None and "presupuesto" in segunda["aviso_respuesta"]


def test_cabecera_del_tunel_solo_se_cree_si_se_confia(web, monkeypatch):
    """Sin ALIADO_CONFIAR_PROXY, cambiar CF-Connecting-IP no regala cuota."""
    codigos = [_get(web + "/api/buscar?q=x", {"CF-Connecting-IP": f"10.0.0.{i}"})[0] for i in range(4)]
    assert codigos[-1] == 429
    publico.reiniciar()
    monkeypatch.setenv("ALIADO_CONFIAR_PROXY", "1")
    codigos = [_get(web + "/api/buscar?q=x", {"CF-Connecting-IP": f"10.0.0.{i}"})[0] for i in range(4)]
    assert codigos == [200] * 4


def test_presupuesto_guarda_solo_el_total(tmp_path):
    p = publico.Presupuesto(5.0, tmp_path / "g.json")
    p.registrar("2026-09", 0.3)
    p.registrar("2026-09", 0.2)
    assert json.loads((tmp_path / "g.json").read_text()) == {"mes": "2026-09", "usd": 0.5}
    assert p.gastado("2026-10") == 0.0  # mes nuevo, contador nuevo
