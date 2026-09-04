"""Servidor web local de Aliado Libre — solo stdlib, sin frameworks (mismo
patrón que NativoWeb en otros proyectos de la suite). Sirve la página en
gui/static/index.html y expone /api/buscar como único endpoint.

El índice (modelo de embeddings + Chroma + BM25) se carga perezosamente en
el primer request de búsqueda, no al arrancar el servidor — así abrir la
página no compite por CPU/memoria hasta que alguien busca de verdad."""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ESTA_CONGELADO = bool(getattr(sys, "frozen", False))


def _raiz_recursos() -> Path:
    """Raíz desde la que colgar recursos (gui/static/...).

    En el .exe de PyInstaller el código vive dentro del archivo comprimido y
    ``__file__`` no apunta a una carpeta real: los datos se extraen a
    ``sys._MEIPASS``. En desarrollo la raíz es la del repositorio."""
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base)
    return Path(__file__).resolve().parent.parent


RAIZ = _raiz_recursos()
if not ESTA_CONGELADO:
    sys.path.insert(0, str(RAIZ))

RAIZ_ESTATICA = RAIZ / "gui" / "static"
PUERTO = 8765

_indice = None
_indice_lock = threading.Lock()


def _crear_indice():
    """Elige índice remoto o local.

    El .exe distribuible NO lleva el corpus, ni Chroma, ni el modelo de
    embeddings: consulta el índice por HTTP (``index.cliente_remoto``), así
    que congelado siempre va por ahí.

    En desarrollo manda ``ALIADO_INDICE_URL``: si está definida se usa el
    servidor remoto, y si no, el índice local del repositorio. Decidirlo por
    la URL y no por si el import funciona es lo único correcto: en el repo el
    import SIEMPRE funciona, así que ese criterio dejaba el índice local
    inalcanzable y rompía el arranque de toda la vida (`python gui/server.py`)
    contra un servidor que puede no estar desplegado.
    """
    hay_url = bool(os.environ.get("ALIADO_INDICE_URL", "").strip())

    if ESTA_CONGELADO or hay_url:
        try:
            from index.cliente_remoto import IndiceRemoto
        except ImportError:
            raise RuntimeError(
                "Esta versión empaquetada necesita el cliente de índice remoto "
                "(index/cliente_remoto.py) y se compiló sin él."
            ) from None
        return IndiceRemoto()

    from index.buscar import IndiceBusqueda

    return IndiceBusqueda()


def _obtener_indice():
    global _indice
    with _indice_lock:
        if _indice is None:
            _indice = _crear_indice()
    return _indice


class Handler(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):  # silencia el log por defecto, ruidoso
        pass

    def do_GET(self):
        ruta = urlparse(self.path)

        if ruta.path == "/api/buscar":
            self._responder_busqueda(ruta)
            return

        if ruta.path == "/api/estado":
            self._responder_json({"cargado": _indice is not None})
            return

        self._servir_estatico(ruta.path)

    def _responder_busqueda(self, ruta):
        params = parse_qs(ruta.query)
        consulta = (params.get("q") or [""])[0].strip()
        if not consulta:
            self._responder_json({"error": "Consulta vacía"}, status=400)
            return

        try:
            k = int((params.get("k") or ["8"])[0])
        except ValueError:
            k = 8

        quiere_respuesta = (params.get("conversacional") or ["0"])[0] == "1"

        try:
            indice = _obtener_indice()
            resultados = indice.buscar(consulta, k=k)
        except Exception as e:
            self._responder_json({"error": str(e)}, status=500)
            return

        salida = {"resultados": resultados}
        if quiere_respuesta:
            from index.responder import responder

            # menos fragmentos que los mostrados: el prompt crece con cada
            # uno y en CPU la respuesta se vuelve notablemente más lenta
            MAX_FRAGMENTOS_CONVERSACIONAL = 4
            usados = resultados[:MAX_FRAGMENTOS_CONVERSACIONAL]
            try:
                texto = responder(consulta, usados)
                # Comprobación determinista antes de mostrar nada: cada número de
                # norma, artículo, plazo o cifra de la respuesta tiene que estar
                # en los fragmentos. Medido sobre 150 respuestas reales, marca 21
                # y las 21 eran malas — ningún falso positivo. No sustituye leer
                # la cita, pero convierte un dato inventado en algo visible en
                # vez de en prosa convincente.
                from index.verificar_anclaje import marcar, verificar

                informe = verificar(texto, usados)
                salida["respuesta"] = texto if informe.anclada else marcar(texto, informe)
                salida["anclada"] = informe.anclada
                if not informe.anclada:
                    salida["aviso_anclaje"] = informe.resumen()
            except RuntimeError as e:
                # modelo GGUF ausente, no cargable o fallo de inferencia:
                # degradar a buscador puro, no tirar toda la respuesta.
                # El mensaje de `responder` ya explica en español qué falta.
                salida["respuesta"] = None
                salida["aviso_respuesta"] = str(e)

        self._responder_json(salida)

    def _servir_estatico(self, ruta_pedida: str) -> None:
        nombre = "index.html" if ruta_pedida in ("/", "") else ruta_pedida.lstrip("/")
        archivo = (RAIZ_ESTATICA / nombre).resolve()

        # nunca servir nada fuera de gui/static/
        if RAIZ_ESTATICA not in archivo.parents and archivo != RAIZ_ESTATICA:
            self.send_error(404)
            return
        if not archivo.is_file():
            self.send_error(404)
            return

        tipo = "text/html" if archivo.suffix == ".html" else "application/octet-stream"
        cuerpo = archivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _responder_json(self, datos: dict, status: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)


def main() -> None:
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler)
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"Aliado Libre corriendo en {url} (Ctrl+C para detener)")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
