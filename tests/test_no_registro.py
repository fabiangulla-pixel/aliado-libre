"""El servicio no registra consultas ni identifica a quien pregunta.

No es una preferencia de estilo: es la promesa central del servicio público
(ver docs/PRINCIPIOS.md). Quien lo usa está preguntando por su despido, su
tutela o su deuda. Lo que no se guarda no se puede filtrar, ni entregar bajo
requerimiento, ni perder en una brecha.

Estos tests fallan si alguien reintroduce el log de acceso por defecto o deja
que un traceback arrastre el texto de la consulta hasta el log.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servidor_indice import server as S

CONSULTA_SENSIBLE = "me despidieron por estar embarazada en la empresa Acme de Cali"
IP_FALSA = "192.0.2.77"


class _ManejadorFalso(S.Handler):
    """Instancia el manejador sin abrir sockets: solo interesa su logging."""

    def __init__(self):  # noqa: D107 - deliberadamente no llama a super()
        self.client_address = (IP_FALSA, 51234)

    def address_string(self):
        return IP_FALSA


def test_no_registra_la_peticion_ni_la_ip(caplog):
    manejador = _ManejadorFalso()
    with caplog.at_level(logging.DEBUG):
        manejador.log_message('"%s" %s %s', f"POST /buscar?q={CONSULTA_SENSIBLE}", "200", "-")
    texto = caplog.text
    assert texto.strip() == "", f"el manejador registró algo: {texto!r}"
    assert IP_FALSA not in texto
    assert "embarazada" not in texto


def test_log_message_no_devuelve_nada_y_no_revienta():
    """Se llama en cada petición: un fallo aquí tumbaría el servidor."""
    assert _ManejadorFalso().log_message("%s", "cualquier cosa") is None


def test_el_error_de_busqueda_no_filtra_la_consulta(caplog, monkeypatch):
    """Un traceback completo puede arrastrar el texto del usuario al log."""

    class _IndiceQueFalla:
        def buscar(self, consulta, k=8):
            raise ValueError(f"detalle interno con la consulta: {consulta}")

    monkeypatch.setattr(S, "obtener_indice", lambda: _IndiceQueFalla())
    monkeypatch.setattr(S, "_TOKEN", None, raising=False)

    import io
    import json as _json

    cuerpo = _json.dumps({"consulta": CONSULTA_SENSIBLE, "n": 5}).encode("utf-8")
    capturado = {}

    class _Manejador(_ManejadorFalso):
        path = "/buscar"
        headers = {"Content-Length": str(len(cuerpo))}
        rfile = io.BytesIO(cuerpo)

        def _autorizado(self):
            return True

        def _error(self, status, mensaje):
            capturado["status"] = status
            capturado["mensaje"] = mensaje

        def _responder_json(self, datos, status=200):
            capturado["datos"] = datos

    manejador = _Manejador()
    with caplog.at_level(logging.DEBUG):
        manejador.do_POST()

    assert capturado["status"] == 500
    assert "embarazada" not in caplog.text, "la consulta llegó al log del servidor"
    assert "embarazada" not in capturado["mensaje"], "la consulta volvió en el mensaje de error"
    assert "Acme" not in caplog.text


def test_el_codigo_no_usa_el_log_de_acceso_por_defecto():
    """Defensa contra reintroducirlo: address_string() no debe aparecer en el log."""
    fuente = (Path(__file__).resolve().parent.parent / "servidor_indice" / "server.py").read_text(
        encoding="utf-8"
    )
    cuerpo_log = fuente.split("def log_message(")[1].split("def ")[0]
    assert "address_string" not in cuerpo_log
    assert "log.info" not in cuerpo_log


@pytest.mark.parametrize("nombre", ["log.exception", "logging.exception"])
def test_sin_tracebacks_completos_en_el_servidor(nombre):
    """`log.exception` vuelca el traceback, que puede contener la consulta."""
    fuente = (Path(__file__).resolve().parent.parent / "servidor_indice" / "server.py").read_text(
        encoding="utf-8"
    )
    assert nombre not in fuente
