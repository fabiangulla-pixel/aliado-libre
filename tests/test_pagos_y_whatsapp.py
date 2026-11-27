"""gui/pagos.py (Wompi) y gui/whatsapp.py (Cloud API): firmas, emisión de
claves y respuestas, todo con servicios falsos. Nunca llama a Wompi ni a Meta."""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest

from gui import pagos, publico, whatsapp

SECRETO_EVENTOS = "test_events_abc"
CREDS = {
    "WOMPI_LLAVE_PUBLICA": "pub_test_123",
    "WOMPI_LLAVE_PRIVADA": "prv_test_123",
    "WOMPI_SECRETO_INTEGRIDAD": "test_integrity_xyz",
    "WOMPI_SECRETO_EVENTOS": SECRETO_EVENTOS,
}


@pytest.fixture()
def wompi(monkeypatch, tmp_path):
    for k, v in CREDS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ALIADO_PAGOS", "wompi")
    monkeypatch.setenv("ALIADO_PRECIOS_COP", json.dumps({"pase-dia": 3500, "inventado": 1}))
    claves = tmp_path / "claves.json"
    monkeypatch.setenv("ALIADO_CLAVES_API", str(claves))
    monkeypatch.setattr(pagos, "RUTA_PENDIENTES", tmp_path / "pagos.json")
    monkeypatch.setattr(pagos, "ARCHIVO_CREDENCIALES", tmp_path / "no_existe.json")
    publico.reiniciar()
    yield claves
    publico.reiniciar()


def _evento(tx: dict, secreto=SECRETO_EVENTOS, timestamp=1764200000):
    props = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
    cadena = f"{tx['id']}{tx['status']}{tx['amount_in_cents']}{timestamp}{secreto}"
    return {
        "event": "transaction.updated",
        "data": {"transaction": tx},
        "signature": {"properties": props, "checksum": hashlib.sha256(cadena.encode()).hexdigest().upper()},
        "timestamp": timestamp,
    }


def test_firma_de_integridad_coincide_con_el_ejemplo_de_wompi():
    assert pagos.firma_integridad(
        "sk8-438k4-xmxm392-sn2m", 2490000, "prod_integrity_Z5mMke9x0k8gpErbDqwrJXMqsI6SFli6"
    ) == ("37c8407747e595535433ef8f6a811d853cd943046624a0ec04662b17bbf33bf5")


def test_solo_se_ofrecen_planes_con_precio_y_que_existen(wompi):
    assert pagos.activo() and pagos.precios() == {"pase-dia": 3500} and pagos.ambiente() == "test"
    with pytest.raises(pagos.ErrorPago):
        pagos.iniciar("gold", "https://x/pago.html")


def test_flujo_completo_pago_aprobado_emite_una_sola_clave(wompi):
    ini = pagos.iniciar("pase-dia", "https://x/pago.html", ahora=1000.0)
    assert "amount-in-cents=350000" in ini["url"] and "signature%3Aintegrity=" in ini["url"]
    tx = {
        "id": "1-abc",
        "status": "APPROVED",
        "amount_in_cents": 350000,
        "reference": ini["referencia"],
        "currency": "COP",
    }
    assert "APPROVED" in pagos.procesar_evento(_evento(tx), None, ahora=1001.0)
    pagos.procesar_evento(_evento(tx), None, ahora=1002.0)  # Wompi repite eventos
    guardadas = json.loads(wompi.read_text())
    assert len(guardadas) == 1  # una sola clave por referencia
    with patch.object(pagos, "consultar_transaccion", return_value=tx):
        r = pagos.estado("1-abc", ahora=1003.0)
    assert r["estado"] == "aprobado" and r["clave"].startswith("al_")
    # la cuota de la web la reconoce sin reiniciar
    assert publico.cuota_busqueda().plan_de(r["clave"]) is not None
    # y en el archivo solo está su hash
    assert r["clave"] not in wompi.read_text()


def test_evento_con_firma_mala_o_monto_distinto_no_emite(wompi):
    ini = pagos.iniciar("pase-dia", "https://x/pago.html")
    tx = {"id": "2-x", "status": "APPROVED", "amount_in_cents": 350000, "reference": ini["referencia"]}
    assert "inválido" in pagos.procesar_evento(_evento(tx, secreto="otro"), None)
    barato = {**tx, "amount_in_cents": 100}
    assert "MONTO_DISTINTO" in pagos.procesar_evento(_evento(barato), None)
    assert not wompi.exists() or json.loads(wompi.read_text()) == {}


def test_pago_rechazado_y_referencia_ajena(wompi):
    ini = pagos.iniciar("pase-dia", "https://x/pago.html")
    tx = {"id": "3-xyz1", "status": "DECLINED", "amount_in_cents": 350000, "reference": ini["referencia"]}
    with patch.object(pagos, "consultar_transaccion", return_value=tx):
        assert pagos.estado("3-xyz1")["estado"] == "rechazado"
    with patch.object(pagos, "consultar_transaccion", return_value={**tx, "reference": "de-otra-tienda"}):
        assert pagos.estado("3-xyz1")["estado"] == "desconocido"
    with pytest.raises(pagos.ErrorPago):
        pagos.estado("../../etc")


def test_pagos_apagados_sin_configuracion(monkeypatch):
    monkeypatch.delenv("ALIADO_PAGOS", raising=False)
    assert pagos.activo() is False


# --- WhatsApp ---------------------------------------------------------------------

EVENTO_WA = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "metadata": {"phone_number_id": "106540352242922"},
                        "messages": [
                            {
                                "from": "573105551234",
                                "id": "wamid.1",
                                "type": "text",
                                "text": {"body": "me cortaron la luz"},
                            },
                            {"from": "573105551234", "id": "wamid.2", "type": "image"},
                        ],
                    },
                    "field": "messages",
                }
            ]
        }
    ],
}


@pytest.fixture()
def wa(monkeypatch, tmp_path):
    monkeypatch.setenv("ALIADO_WHATSAPP", "1")
    monkeypatch.setenv("ALIADO_WA_TOKEN", "tok")
    monkeypatch.setenv("ALIADO_WA_APP_SECRET", "secreto")
    monkeypatch.setenv("ALIADO_WA_VERIFY_TOKEN", "verifica")
    monkeypatch.setenv("ALIADO_WA_TOPE_MES", "2")
    monkeypatch.setattr(whatsapp, "RUTA_USO", tmp_path / "uso.json")
    monkeypatch.setattr(whatsapp, "_cuota", None)
    whatsapp._vistos.clear()
    yield


def test_verificacion_de_suscripcion(wa):
    ok = {"hub.mode": ["subscribe"], "hub.verify_token": ["verifica"], "hub.challenge": ["123"]}
    assert whatsapp.verificar_suscripcion(ok) == "123"
    assert whatsapp.verificar_suscripcion({**ok, "hub.verify_token": ["otro"]}) is None


def test_firma_del_webhook():
    cuerpo = json.dumps(EVENTO_WA).encode()
    firma = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
    assert whatsapp.firma_valida(cuerpo, firma, "secreto")
    assert not whatsapp.firma_valida(cuerpo + b" ", firma, "secreto")
    assert not whatsapp.firma_valida(cuerpo, None, "secreto")


def test_solo_mensajes_de_texto():
    (m,) = whatsapp.mensajes_de_texto(EVENTO_WA)
    assert m["texto"] == "me cortaron la luz" and m["phone_number_id"] == "106540352242922"


def test_atender_responde_deduplica_y_respeta_el_cupo_del_mes(wa):
    (m,) = whatsapp.mensajes_de_texto(EVENTO_WA)
    resultados = [
        {
            "titulo_documento": "Ley 142 de 1994",
            "texto": "Artículo 140. Suspensión…",
            "url_original": "https://f",
        }
    ]
    with patch.object(whatsapp, "enviar") as enviar:
        texto = whatsapp.atender(m, lambda q: (resultados, True))
        assert "Ley 142 de 1994" in texto and "https://f" in texto and len(texto) <= whatsapp.MAX_TEXTO
        assert whatsapp.atender(m, lambda q: (resultados, True)) is None  # reintento de Meta
        whatsapp.atender({**m, "id": "wamid.9"}, lambda q: (resultados, True))
        assert whatsapp.atender({**m, "id": "wamid.10"}, lambda q: (resultados, True)) is None  # tope 2
    assert enviar.call_count == 2
    # del número no queda rastro en el archivo de uso
    assert "573105551234" not in whatsapp.RUTA_USO.read_text()


def test_sin_respaldo_se_dice_y_norma_que_no_rige_se_marca():
    r = [
        {
            "titulo_documento": "Ley 1943 de 2018",
            "texto": "x",
            "vigencia": {"estado": "inexequible", "alcance": "documento"},
        }
    ]
    texto = whatsapp.componer_respuesta("impuestos", r, False, "")
    assert "solo como pista" in texto and "INEXEQUIBLE" in texto
