"""Prueba de punta a punta del .exe YA COMPILADO, con el modelo real al lado.

Esto es lo único que ningún test con dobles puede demostrar: que dentro del
binario congelado (a) se resuelve la ruta a ``modelo/`` a partir de
``sys.executable``, (b) las DLL nativas de llama-cpp que empacó PyInstaller
cargan de verdad, y (c) el cliente del índice remoto habla con un servidor.

Levanta un servidor de índice FALSO (devuelve fragmentos fijos, con el mismo
esquema que ``servidor_indice``) para no tener que cargar los 9 GB del índice
real, apunta el .exe a él y le pide una búsqueda con redacción por IA. Si el
.exe devuelve una respuesta redactada, todo el camino congelado funciona.

Uso:  ./venv/Scripts/python.exe scripts/probar_exe_end_to_end.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXE = RAIZ / "dist" / "AliadoLibre.exe"
PUERTO_INDICE = 8799
PUERTO_GUI = 8765

FRAGMENTOS = [
    {
        "texto": (
            "Artículo 24. Encargo. Mientras se surte el proceso de selección para "
            "proveer empleos de carrera administrativa, los empleados de carrera "
            "tendrán derecho a ser encargados de tales empleos. El encargo no podrá "
            "ser superior a seis (6) meses."
        ),
        "identificador": "Ley 909 de 2004",
        "titulo": "Ley 909 de 2004, artículo 24",
        "fuente": "gestor_normativo",
        "url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=14861",
    },
]


class ManejadorFalso(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # silencio
        pass

    def do_GET(self):
        self._json({"estado": "listo", "fragmentos": len(FRAGMENTOS), "segundos_carga": 0.0})

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        self._json({"consulta": cuerpo.get("consulta", ""), "n": len(FRAGMENTOS), "resultados": FRAGMENTOS})

    def _json(self, datos: dict):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)


def main() -> int:
    if not EXE.exists():
        print(f"No existe {EXE} — compilar primero con scripts/build_exe.py")
        return 1
    gguf = RAIZ / "dist" / "modelo"
    if not any(gguf.glob("*.gguf")):
        print(f"No hay ningún .gguf en {gguf} — copiar el modelo al lado del .exe")
        return 1

    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO_INDICE), ManejadorFalso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    print(f"Servidor de índice falso en 127.0.0.1:{PUERTO_INDICE}")

    entorno = dict(os.environ)
    entorno["ALIADO_INDICE_URL"] = f"http://127.0.0.1:{PUERTO_INDICE}"
    entorno.pop("ALIADO_INDICE_TOKEN", None)

    proceso = subprocess.Popen(
        [str(EXE)],
        env=entorno,
        cwd=str(EXE.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    codigo = 1
    try:
        base = f"http://127.0.0.1:{PUERTO_GUI}"
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/estado", timeout=2).read()
                break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        else:
            print("El .exe no levantó el servidor en 60s")
            return 1
        print("El .exe respondió en /api/estado")

        consulta = "¿Cuánto puede durar un encargo en carrera administrativa?"
        url = base + "/api/buscar?" + urllib.parse.urlencode({"q": consulta, "conversacional": "1"})
        print("Pidiendo búsqueda con redacción por IA (carga 940 MB en CPU, puede tardar ~2 min)...")
        inicio = time.time()
        datos = json.loads(urllib.request.urlopen(url, timeout=900).read().decode("utf-8"))
        print(f"Respondió en {time.time() - inicio:.0f}s")
        print("resultados:", len(datos.get("resultados", [])))
        respuesta = datos.get("respuesta")
        if respuesta:
            print("\n--- RESPUESTA REDACTADA POR EL .EXE ---")
            print(respuesta)
            print("---------------------------------------")
            codigo = 0
        else:
            print("\nEl .exe NO redactó respuesta.")
            print("aviso:", datos.get("aviso_respuesta"))
            print("error:", datos.get("error"))
    finally:
        proceso.terminate()
        try:
            salida = proceso.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            proceso.kill()
            salida = ""
        servidor.shutdown()
        if salida:
            print("\n--- salida del .exe ---")
            print(salida[-3000:])
    return codigo


if __name__ == "__main__":
    sys.exit(main())
