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

# Hasta MAX_DRENAJE se drena un cuerpo ya rechazado, para poder contestar el 413;
# pasado ese tope se corta y el cliente puede no llegar a ver el mensaje. Vive en
# drenar_cuerpo porque gui/server.py tiene el mismo problema. El import va aquí,
# tras el sys.path.insert, porque de otro modo no se encuentra al arrancar el
# servidor por ruta (python servidor_indice/server.py).
from drenar_cuerpo import MAX_DRENAJE, descartar_cuerpo  # noqa: E402

PUERTO_DEFECTO = 8800
MAX_CUERPO = 64 * 1024  # una consulta jurídica no se acerca; corta abusos
N_DEFECTO = 8
N_MAXIMO = 50  # evita que un cliente pida 10.000 fragmentos y tumbe el servidor

# Reordenar con un cross-encoder sube el recall@5 de 33,5% a 41,0% sobre las 200
# consultas apartadas (McNemar p=0,0081), y en @8 de 37,5% a 48,5% (p=0,0001).
# Es la unica mejora de recuperacion confirmada en datos que no se usaron para
# elegir nada. Cifras en docs/PROJECT_STATE.md.
#
# Aqui viene APAGADO a proposito, y es lo que separa al servidor del modo
# escritorio. En el equipo del usuario reordenar se enciende solo cuando hay GPU
# (0,66 s medidos: sale gratis). En el servidor cuesta ~57 s por consulta en CPU
# y ~2,3 GB de RAM mas, y encenderlo es una decision de factura que se toma a
# sabiendas, no un efecto secundario de actualizar: main() fija
# ALIADO_RERANKER_ACTIVO="0" si el operador no dijo nada, y con eso el servidor
# queda fuera de la regla automatica de index.reordenar.activo().
# Para encenderlo: ALIADO_RERANKER_ACTIVO=1 (y ALIADO_RERANKER_CANDIDATOS para
# el tamano de ventana; 40 es lo medido).
VERDADEROS = {"1", "true", "si", "sí"}

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


def reranker_activo() -> bool:
    """Se lee en cada petición, no al importar: así un test puede activarlo y el
    valor no queda congelado en el momento del import."""
    return os.environ.get("ALIADO_RERANKER_ACTIVO", "").strip().lower() in VERDADEROS


def quedarse_fuera_de_la_regla_automatica() -> None:
    """El servidor NO hereda el "se enciende si hay GPU" del modo escritorio.

    En el equipo del usuario reordenar se enciende solo cuando hay GPU porque
    cuesta 0,66 s y no lo paga nadie. Aqui lo paga una factura por segundo de
    CPU o de GPU alquilada, y esa decision se toma a sabiendas, no porque el
    host de turno traiga aceleradora. Se llama en main(), o sea una vez por
    proceso y antes de la primera busqueda.

    Es setdefault y no una asignacion: el operador que si lo pidio sigue
    mandando.
    """
    os.environ.setdefault("ALIADO_RERANKER_ACTIVO", "0")


def token_configurado() -> str | None:
    token = os.environ.get("ALIADO_INDICE_TOKEN", "").strip()
    return token or None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AliadoLibreIndice/1.0"
    # Se pone en True en cuanto se lee el cuerpo. Sin esta marca, un error
    # posterior (un 400 por JSON inválido, por ejemplo) volvería a leer
    # Content-Length bytes que ya no van a llegar, y la petición se colgaría
    # hasta el timeout.
    cuerpo_consumido = False

    def log_message(self, formato, *args):
        """No registra nada. A propósito, y es una decisión de producto.

        El log de acceso por defecto de BaseHTTPRequestHandler incluye la IP
        del cliente y la línea de petición. Quien consulta este servicio está
        preguntando por su despido, su tutela o su deuda: la IP más la hora es
        un dato sensible aunque la consulta viaje en el cuerpo y no en la URL.
        Lo que no se guarda no se puede filtrar, ni entregar bajo requerimiento,
        ni perder en una brecha.

        Ver docs/PRINCIPIOS.md. tests/test_no_registro.py protege esto.
        """
        return

    # -- utilidades ------------------------------------------------------

    def _descartar_cuerpo(self) -> None:
        """Delega en drenar_cuerpo, que es el sitio unico donde vive esta regla.

        Estuvo aqui hasta que el mismo defecto aparecio tambien en gui/server.py.
        """
        if descartar_cuerpo(self, MAX_DRENAJE):
            self.cuerpo_consumido = True

    def _responder_json(self, datos: dict, status: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _error(self, status: int, mensaje: str) -> None:
        self._descartar_cuerpo()
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
        # El handler se reutiliza entre peticiones de una misma conexión
        # keep-alive: la marca es de esta petición, no del socket.
        self.cuerpo_consumido = False
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
                    "reranker": reranker_activo(),
                }
            )
            return

        if ruta == "/buscar":
            self._metodo_no_permitido("POST")
            return

        self._error(404, f"Ruta desconocida: {ruta}")

    def do_POST(self):  # noqa: N802
        self.cuerpo_consumido = False
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
        self.cuerpo_consumido = True
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

        fuentes = datos.get("fuentes")
        if fuentes is not None:
            if not isinstance(fuentes, list) or not all(isinstance(f, str) for f in fuentes):
                self._error(400, "El campo 'fuentes' debe ser una lista de textos.")
                return
            from index.fuentes import normalizar

            fuentes = normalizar(fuentes)

        try:
            texto = consulta.strip()
            # Reordenar (o no) lo decide IndiceBusqueda.buscar leyendo
            # ALIADO_RERANKER_ACTIVO, que main() fija a "0" si el operador no
            # dijo nada. Aqui no se duplica: tener dos sitios que ensanchan la
            # ventana y reordenan es tener dos sitios donde se desincroniza.
            resultados = obtener_indice().buscar(texto, k=n, fuentes=fuentes)
        except RuntimeError as e:
            self._error(503, str(e))
            return
        except Exception as e:  # el índice puede fallar por disco o corrupción
            # Sin traza completa y sin la consulta: un traceback puede arrastrar
            # el texto que escribió el usuario hasta el log del servidor, que es
            # justo lo que este servicio promete no guardar.
            log.error("Fallo buscando en el índice: %s", type(e).__name__)
            self._error(500, f"Error buscando en el índice: {type(e).__name__}")
            return

        self._responder_json(
            {
                "consulta": consulta.strip(),
                "n": n,
                "fuentes": fuentes or [],
                "resultados": resultados,
            }
        )

    def _metodo_no_permitido(self, permitidos: str) -> None:
        self._descartar_cuerpo()
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

    quedarse_fuera_de_la_regla_automatica()
    log.info("Reordenado con cross-encoder: %s", "activo" if reranker_activo() else "apagado")

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
