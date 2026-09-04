"""Prueba que la app local (gui/server.py) funciona de punta a punta contra el
índice REAL del repositorio: levanta el servidor, consulta y pide redacción por
IA con el modelo GGUF local.

No abre navegador ni simula clics: habla con los endpoints, que es donde de
verdad está el comportamiento.

Uso:  ./venv/Scripts/python.exe scripts/probar_gui_local.py ["consulta"]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUERTO = 8765
BASE = f"http://127.0.0.1:{PUERTO}"


def _puerto_ocupado(puerto: int) -> bool:
    """Un proceso ajeno escuchando en el puerto haría que la sonda le hablara a
    él y no al programa que se quiere probar: un falso resultado, positivo o
    negativo. Mejor abortar."""
    import socket

    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _matar_arbol(proceso) -> str:
    """`terminate()` no basta con un .exe onefile de PyInstaller: el bootloader
    lanza un proceso HIJO que es el que realmente corre la aplicación y sobrevive
    a que se mate al padre, dejando el puerto ocupado. Hay que matar el árbol.
    """
    import subprocess as _sp

    salida = ""
    try:
        if sys.platform == "win32":
            _sp.run(
                ["taskkill", "/PID", str(proceso.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            proceso.terminate()
        salida = proceso.communicate(timeout=20)[0] or ""
    except Exception:
        proceso.kill()
    return salida


def main() -> int:
    POR_DEFECTO = "¿Cuánto puede durar un encargo en un empleo de carrera administrativa?"
    consulta = " ".join(sys.argv[1:]) or POR_DEFECTO

    if _puerto_ocupado(PUERTO):
        print(
            f"El puerto {PUERTO} ya está ocupado por otro proceso (¿una instancia "
            "anterior de la app o del .exe?). Ciérralo: si no, esta prueba le hablaría "
            "a él y el resultado no significaría nada."
        )
        return 1

    entorno = dict(os.environ)
    # sin esta variable, gui/server.py usa el índice LOCAL, que es lo que se
    # quiere probar aquí; con ella iría contra un servidor remoto.
    entorno.pop("ALIADO_INDICE_URL", None)

    proceso = subprocess.Popen(
        [str(RAIZ / "venv" / "Scripts" / "python.exe"), str(RAIZ / "gui" / "server.py")],
        cwd=str(RAIZ),
        env=entorno,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/estado", timeout=2).read()
                break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        else:
            print("El servidor no levantó en 60s")
            return 1
        print("Servidor arriba.")

        url = BASE + "/api/buscar?" + urllib.parse.urlencode({"q": consulta, "conversacional": "1"})
        print(f"Consulta: {consulta}")
        print("Cargando índice (~2,3 GB, la primera vez tarda) y redactando en CPU...")
        inicio = time.time()
        try:
            crudo = urllib.request.urlopen(url, timeout=1800).read()
        except urllib.error.HTTPError as e:
            # el cuerpo del 500 trae el mensaje real; sin leerlo solo se ve
            # "Internal Server Error", que no dice nada
            print("HTTP", e.code, "->", e.read().decode("utf-8", "replace")[:800])
            return 1
        datos = json.loads(crudo.decode("utf-8"))
        print(f"Respondió en {time.time() - inicio:.0f}s\n")

        if datos.get("error"):
            print("ERROR:", datos["error"])
            return 1

        resultados = datos.get("resultados", [])
        print(f"{len(resultados)} fragmentos recuperados del índice real:")
        for r in resultados[:4]:
            ident = r.get("identificador_documento") or r.get("titulo_documento") or "(sin id)"
            print(f"  - {ident}  [{r.get('fuente', '?')}]")

        if datos.get("respuesta"):
            print("\n--- RESPUESTA REDACTADA ---")
            print(datos["respuesta"])
            print("---------------------------")
            return 0
        print("\nSin respuesta redactada. aviso:", datos.get("aviso_respuesta"))
        return 1
    finally:
        _matar_arbol(proceso)


if __name__ == "__main__":
    sys.exit(main())
