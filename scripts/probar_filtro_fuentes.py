"""Prueba el filtro por fuente contra el índice REAL.

Lo que hay que demostrar no es que el parámetro viaje —eso ya lo cubren los
tests con dobles— sino que filtrar de verdad **cambia lo que se recupera** y
que una fuente pequeña (la SIC es el 0,7% del corpus) sigue devolviendo
resultados cuando se la aísla. Ese es justamente el caso que un filtro mal
implementado rompe: sin holgura al pedir candidatos, la SIC no aparece nunca.

Uso:  ./venv/Scripts/python.exe scripts/probar_filtro_fuentes.py
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

CONSULTAS = [
    ("proteccion al consumidor garantia de un producto defectuoso", ["sic"]),
    ("retencion en la fuente sobre honorarios", ["dian"]),
    ("derecho fundamental a la salud tutela", ["corte_constitucional"]),
    ("posicion dominante y practicas restrictivas", ["sic", "dian"]),
]


def _puerto_ocupado(puerto: int) -> bool:
    import socket

    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _matar(proceso) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(proceso.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            proceso.terminate()
        proceso.communicate(timeout=20)
    except Exception:
        proceso.kill()


def _buscar(consulta: str, fuentes: list[str] | None) -> dict:
    params = {"q": consulta, "k": "8"}
    if fuentes:
        params["fuentes"] = ",".join(fuentes)
    url = BASE + "/api/buscar?" + urllib.parse.urlencode(params)
    try:
        return json.loads(urllib.request.urlopen(url, timeout=900).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode("utf-8", "replace")[:300]}


def main() -> int:
    if _puerto_ocupado(PUERTO):
        print(f"El puerto {PUERTO} ya está ocupado; ciérralo antes de correr esta prueba.")
        return 1

    entorno = dict(os.environ)
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
    fallos = 0
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/api/estado", timeout=2).read()
                break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        else:
            print("El servidor no levantó")
            return 1

        catalogo = json.loads(urllib.request.urlopen(BASE + "/api/fuentes", timeout=60).read())
        print(
            f"/api/fuentes: {len(catalogo['fuentes'])} fuentes, "
            f"{catalogo['total_fragmentos']:,} fragmentos".replace(",", ".")
        )
        for f in catalogo["fuentes"]:
            print(f"   {f['nombre']:26} {f['fragmentos']:>7}")
        print(f"   ausentes declaradas: {len(catalogo['ausentes'])}\n")

        for consulta, fuentes in CONSULTAS:
            datos = _buscar(consulta, fuentes)
            if datos.get("error"):
                print(f"ERROR en {fuentes}: {datos['error']}")
                fallos += 1
                continue
            resultados = datos.get("resultados", [])
            obtenidas = {r.get("fuente") for r in resultados}
            ok = bool(resultados) and obtenidas <= set(fuentes)
            print(
                f"[{'OK  ' if ok else 'FALLO'}] {'+'.join(fuentes):28} "
                f"{len(resultados)} resultados, fuentes devueltas: {sorted(obtenidas)}"
            )
            if resultados:
                print(f"         1º: {resultados[0].get('identificador_documento') or '(sin id)'}")
            if not ok:
                fallos += 1

        # sin filtro debe traer variedad
        datos = _buscar("terminacion del contrato de trabajo", None)
        variedad = {r.get("fuente") for r in datos.get("resultados", [])}
        n = len(datos.get("resultados", []))
        print(f"\n[sin filtro] {n} resultados de {len(variedad)} fuentes distintas")
    finally:
        _matar(proceso)

    print("\nTODO BIEN" if fallos == 0 else f"\n{fallos} comprobaciones fallaron")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
