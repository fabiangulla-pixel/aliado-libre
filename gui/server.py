"""Servidor web local de Aliado Libre — solo stdlib, sin frameworks (mismo
patrón que NativoWeb en otros proyectos de la suite). Sirve la página en
gui/static/index.html y expone /api/buscar como único endpoint.

El índice (modelo de embeddings + Chroma + BM25) se carga perezosamente en
el primer request de búsqueda, no al arrancar el servidor — así abrir la
página no compite por CPU/memoria hasta que alguien busca de verdad."""

from __future__ import annotations

import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RAIZ_ESTATICA = Path(__file__).resolve().parent / "static"
PUERTO = 8765

_indice = None
_indice_lock = threading.Lock()


def _obtener_indice():
    global _indice
    with _indice_lock:
        if _indice is None:
            from index.buscar import IndiceBusqueda

            _indice = IndiceBusqueda()
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

        try:
            indice = _obtener_indice()
            resultados = indice.buscar(consulta, k=k)
            self._responder_json({"resultados": resultados})
        except Exception as e:
            self._responder_json({"error": str(e)}, status=500)

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
