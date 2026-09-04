"""Compila el .exe de Aliado Libre con PyInstaller.

Se hace desde un script y no a mano porque hay dos pasos que en este proyecto
NO son opcionales:

1. Borrar ``build/`` y ``dist/`` y pasar ``--clean``. PyInstaller reutiliza el
   análisis cacheado, y con un .spec que cambia sus ``excludes`` eso deja
   dentro del binario módulos que ya se habían quitado: se compila "bien" y el
   .exe sigue pesando de más.
2. Usar el intérprete del venv (Python 3.12). El Python del sistema (3.14)
   revienta con PyTorch en este equipo, y además no tiene las dependencias.

Uso:  ./venv/Scripts/python.exe scripts/build_exe.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SPEC = RAIZ / "aliado_libre.spec"
DIST = RAIZ / "dist"
BUILD = RAIZ / "build"


def limpiar() -> None:
    for carpeta in (BUILD, DIST):
        if carpeta.exists():
            print(f"[limpieza] borrando {carpeta}")
            shutil.rmtree(carpeta)


def compilar() -> int:
    # Nunca se relanza un proceso con sys.executable desde el .exe ya
    # congelado (eso sería una bomba fork); aquí estamos en el repositorio,
    # no dentro del binario, y PyInstaller se invoca en proceso.
    if getattr(sys, "frozen", False):
        raise RuntimeError("Este script solo se ejecuta desde el repositorio, nunca desde el .exe.")

    import PyInstaller.__main__

    PyInstaller.__main__.run(
        [
            str(SPEC),
            "--clean",
            "--noconfirm",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD),
        ]
    )
    return 0


def informar() -> None:
    exe = DIST / "AliadoLibre.exe"
    if not exe.exists():
        print("ERROR: no se generó dist/AliadoLibre.exe")
        raise SystemExit(1)
    mb = exe.stat().st_size / (1024 * 1024)
    print(f"\n[ok] {exe}  ({mb:.1f} MB)")
    modelo = DIST / "modelo"
    if not modelo.exists():
        print(
            "[aviso] falta dist/modelo/ con el GGUF Q4_K_M. El .exe arranca, pero "
            "la capa conversacional local no funcionará hasta copiarlo (ver docs/EMPAQUETADO.md)."
        )


if __name__ == "__main__":
    limpiar()
    compilar()
    informar()
