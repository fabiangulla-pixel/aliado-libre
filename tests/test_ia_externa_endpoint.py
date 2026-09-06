"""El endpoint /api/responder: estima antes de gastar y no filtra la clave.

Con dobles del proveedor: no se llama a ninguna API ni se gasta dinero.
"""

from __future__ import annotations

import json
import sys
import threading
import types
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from gui import server as gsrv

CLAVE = "sk-ant-EstoEsSecretoDeVerdad0123456789"
FRAGMENTOS = [
    {
        "id": "gestor_normativo:1::frag0",
        "texto": "Ley 909 de 2004, artículo 24. El encargo no podrá ser superior a seis (6) meses.",
        "identificador_documento": "Ley 909 de 2004",
        "titulo_documento": "Ley 909 de 2004",
        "fuente": "gestor_normativo",
        "puntaje": 0.09,
    }
]


@pytest.fixture()
def base():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), gsrv.Handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


def _post(base, cuerpo):
    peticion = urllib.request.Request(
        base + "/api/responder",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(peticion, timeout=10).read().decode("utf-8"))


def _proveedor_falso(monkeypatch, texto="Según la Ley 909 de 2004, artículo 24, son seis (6) meses."):
    from index import proveedores

    visto = {}

    def _generar(prompt, sistema, proveedor, clave=None, modelo=None):
        visto.update(prompt=prompt, sistema=sistema, proveedor=proveedor, clave=clave, modelo=modelo)
        usage = types.SimpleNamespace(input_tokens=1200, output_tokens=300)
        return proveedores.RespuestaProveedor(texto, usage, proveedor, modelo or "claude-haiku-4-5")

    monkeypatch.setattr(proveedores, "generar", _generar)
    return visto


def test_solo_estimar_no_llama_al_proveedor_ni_pide_clave(base, monkeypatch):
    visto = _proveedor_falso(monkeypatch)
    datos = _post(
        base,
        {
            "consulta": "cuánto dura un encargo",
            "fragmentos": FRAGMENTOS,
            "proveedor": "claude",
            "solo_estimar": True,
        },
    )
    assert visto == {}, "el estimado no debe llamar al proveedor"
    est = datos["estimado"]
    assert est["estimado"] is True
    assert est["usd"] > 0
    assert est["pesos"] >= 0
    assert "estimado" in est["texto"].lower()


def test_responder_devuelve_el_costo_real(base, monkeypatch):
    _proveedor_falso(monkeypatch)
    datos = _post(
        base,
        {
            "consulta": "cuánto dura un encargo",
            "fragmentos": FRAGMENTOS,
            "proveedor": "claude",
            "clave": CLAVE,
        },
    )
    assert datos["respuesta"].startswith("Según la Ley 909")
    costo = datos["costo"]
    assert costo["estimado"] is False
    assert costo["tokens_entrada"] == 1200
    assert "real" in costo["texto"].lower()


def test_el_prompt_no_duplica_el_sistema(base, monkeypatch):
    """construir_prompt() ya incluye PROMPT_SISTEMA; los proveedores externos
    lo reciben por su propio parámetro, así que el prompt no debe repetirlo."""
    visto = _proveedor_falso(monkeypatch)
    _post(
        base,
        {"consulta": "algo", "fragmentos": FRAGMENTOS, "proveedor": "claude", "clave": CLAVE},
    )
    from index.responder import PROMPT_SISTEMA

    assert visto["sistema"] == PROMPT_SISTEMA
    assert PROMPT_SISTEMA not in visto["prompt"]


def test_la_clave_llega_al_proveedor_pero_no_vuelve_en_la_respuesta(base, monkeypatch):
    visto = _proveedor_falso(monkeypatch)
    datos = _post(
        base,
        {"consulta": "algo", "fragmentos": FRAGMENTOS, "proveedor": "claude", "clave": CLAVE},
    )
    assert visto["clave"] == CLAVE
    assert CLAVE not in json.dumps(datos)


def test_un_fallo_del_proveedor_da_502_sin_la_clave(base, monkeypatch):
    from index import proveedores

    def _revienta(*a, **k):
        raise proveedores.ErrorProveedor("claude falló (RuntimeError): x-api-key: [clave omitida]")

    monkeypatch.setattr(proveedores, "generar", _revienta)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(
            base,
            {"consulta": "algo", "fragmentos": FRAGMENTOS, "proveedor": "claude", "clave": CLAVE},
        )
    assert exc.value.code == 502
    assert CLAVE not in exc.value.read().decode("utf-8")


def test_faltan_campos_da_400(base):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, {"consulta": "algo"})
    assert exc.value.code == 400


def test_la_respuesta_externa_tambien_pasa_por_el_verificador(base, monkeypatch):
    """Una IA cara también puede citar la norma equivocada."""
    _proveedor_falso(monkeypatch, texto="Según el Decreto 605 de 1996 son quince (15) días.")
    datos = _post(
        base,
        {"consulta": "algo", "fragmentos": FRAGMENTOS, "proveedor": "claude", "clave": CLAVE},
    )
    assert datos["anclada"] is False
    assert "no está en las fuentes citadas" in datos["respuesta"]


def test_otras_rutas_post_dan_404(base):
    peticion = urllib.request.Request(
        base + "/api/otra", data=b"{}", method="POST", headers={"Content-Type": "application/json"}
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(peticion, timeout=10)
    assert exc.value.code == 404
