"""Servidor HTTP del índice: expone `IndiceBusqueda.buscar()` por red.

Solo stdlib, sin frameworks — mismo patrón que gui/server.py y el resto de
la suite. A diferencia de gui/server.py, aquí el índice se carga UNA vez al
arrancar (no perezosamente): este proceso no existe para otra cosa, y así
el primer usuario no paga los ~30-60s de carga del modelo y de Chroma.

Endpoints:
  GET  /salud   -> estado del índice (fragmentos, segundos de carga)
  POST /buscar  -> {"consulta": str, "n": int} -> {"resultados": [fragmento...]}

Cada fragmento es EXACTAMENTE el dict que devuelve hoy IndiceBusqueda.buscar():
{"id", "puntaje", "texto", + metadatos del corpus (titulo_documento, fuente,
identificador_documento, url_original, ...)}. No se reordena ni se recorta
nada, para que index/cliente_remoto.py sea un reemplazo transparente del
índice local.

Autenticación: token compartido en `Authorization: Bearer <token>`, leído de
la variable de entorno ALIADO_INDICE_TOKEN. Si no está definida el servidor
arranca ABIERTO y lo advierte por log (útil en local; nunca en internet).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PUERTO_DEFECTO = 8800
MAX_CUERPO = 64 * 1024  # una consulta jurídica no se acerca; corta abusos
N_DEFECTO = 8
N_MAXIMO = 50  # evita que un cliente pida 10.000 fragmentos y tumbe el servidor

log = logging.getLogger("servidor_indice")

# Estado del proceso. `_indice` lo inyecta cargar_indice() al arrancar; los
# tests lo sustituyen por un doble sin tocar los 9GB reales.
_indice = None
_segundos_carga: float | None = None
_total_fragmentos: int | None = None


def obtener_indice():
    if _indice is None:
        raise RuntimeError("El índice todavía no está cargado en este servidor.")
    return _indice


def cargar_indice() -> None:
    """Construye el IndiceBusqueda real. Se importa aquí dentro a propósito:
    importar index.buscar arrastra torch y sentence_transformers, y los tests
    del servidor no deben pagar eso."""
    global _indice, _segundos_carga, _total_fragmentos

    from index.buscar import IndiceBusqueda

    inicio = time.monotonic()
    _indice = IndiceBusqueda()
    _segundos_carga = round(time.monotonic() - inicio, 2)
    _total_fragmentos = getattr(_indice, "_total", None)
    log.info("Índice cargado: %s fragmentos en %ss", _total_fragmentos, _segundos_carga)


def token_configurado() -> str | None:
    token = os.environ.get("ALIADO_INDICE_TOKEN", "").strip()
    return token or None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AliadoLibreIndice/1.0"

    def log_message(self, formato, *args):
        log.info("%s - %s", self.address_string(), formato % args)

    # -- utilidades ------------------------------------------------------

    def _responder_json(self, datos: dict, status: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _error(self, status: int, mensaje: str) -> None:
        self._responder_json({"error": mensaje}, status=status)

    def _autorizado(self) -> bool:
        """True si la petición puede pasar. Con ALIADO_INDICE_TOKEN definida
        exige `Authorization: Bearer <token>`; sin ella, todo pasa."""
        esperado = token_configurado()
        if esperado is None:
            return True
        cabecera = self.headers.get("Authorization", "")
        if not cabecera.startswith("Bearer "):
            return False
        # comparación en tiempo constante: es un secreto compartido
        return compare_digest(cabecera[7:].strip(), esperado)

    # -- rutas -----------------------------------------------------------

    def do_GET(self):  # noqa: N802 (nombre impuesto por BaseHTTPRequestHandler)
        ruta = urlparse(self.path).path.rstrip("/") or "/"

        if ruta == "/salud":
            if not self._autorizado():
                self._error(401, "Token ausente o inválido.")
                return
            self._responder_json(
                {
                    "estado": "listo" if _indice is not None else "sin_indice",
                    "fragmentos": _total_fragmentos,
                    "segundos_carga": _segundos_carga,
                    "autenticado": token_configurado() is not None,
                }
            )
            return

        if ruta == "/buscar":
            self._metodo_no_permitido("POST")
            return

        self._error(404, f"Ruta desconocida: {ruta}")

    def do_POST(self):  # noqa: N802
        ruta = urlparse(self.path).path.rstrip("/") or "/"

        if ruta == "/salud":
            self._metodo_no_permitido("GET")
            return

        if ruta != "/buscar":
            self._error(404, f"Ruta desconocida: {ruta}")
            return

        if not self._autorizado():
            self._error(401, "Token ausente o inválido.")
            return

        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._error(400, "Content-Length inválido.")
            return
        if largo > MAX_CUERPO:
            self._error(413, "Cuerpo demasiado grande.")
            return

        crudo = self.rfile.read(largo) if largo > 0 else b""
        try:
            datos = json.loads(crudo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "El cuerpo no es JSON válido.")
            return
        if not isinstance(datos, dict):
            self._error(400, "El cuerpo debe ser un objeto JSON.")
            return

        consulta = datos.get("consulta")
        if not isinstance(consulta, str) or not consulta.strip():
            self._error(400, "Falta el campo 'consulta' (texto no vacío).")
            return

        n = datos.get("n", N_DEFECTO)
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            self._error(400, "El campo 'n' debe ser un entero mayor o igual a 1.")
            return
        n = min(n, N_MAXIMO)

        try:
            resultados = obtener_indice().buscar(consulta.strip(), k=n)
        except RuntimeError as e:
            self._error(503, str(e))
            return
        except Exception as e:  # el índice puede fallar por disco o corrupción
            log.exception("Fallo buscando")
            self._error(500, f"Error buscando en el índice: {e}")
            return

        self._responder_json({"consulta": consulta.strip(), "n": n, "resultados": resultados})

    def _metodo_no_permitido(self, permitidos: str) -> None:
        cuerpo = json.dumps({"error": f"Método no permitido. Use {permitidos}."}).encode("utf-8")
        self.send_response(405)
        self.send_header("Allow", permitidos)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if token_configurado() is None:
        log.warning(
            "ALIADO_INDICE_TOKEN no está definida: el servidor queda ABIERTO a "
            "cualquiera que alcance el puerto. Defínela antes de exponerlo a internet."
        )

    puerto = int(os.environ.get("PORT") or PUERTO_DEFECTO)
    cargar_indice()

    servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Handler)
    log.info("Servidor del índice escuchando en el puerto %s", puerto)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log.info("Cerrando.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
