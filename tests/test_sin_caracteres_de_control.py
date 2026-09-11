"""Ningun archivo fuente debe traer caracteres de control invisibles.

El 10-sep-2026 un `\b` escrito desde un heredoc acabo como byte 0x08 dentro de
una expresion regular de `ingest/chunking.py`. La rama afectada quedo muerta —
pedia un caracter que ningun documento contiene — y no fallo nada: los tests
cubrian la otra rama. Es una clase entera de fallo silencioso, y se corta aqui.
"""

import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PERMITIDOS = {"\n", "\t", "\r"}
IGNORAR = {".venv", ".venv312", ".git", "__pycache__", "dist", "build", "chroma_db"}


def _fuentes():
    for ruta in RAIZ.rglob("*.py"):
        if any(parte in IGNORAR or parte.startswith("chroma_db") for parte in ruta.parts):
            continue
        yield ruta


def test_ningun_py_trae_caracteres_de_control():
    sucios = {}
    for ruta in _fuentes():
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        malos = sorted({c for c in set(texto) if unicodedata.category(c) == "Cc" and c not in PERMITIDOS})
        if malos:
            sucios[str(ruta.relative_to(RAIZ))] = [hex(ord(c)) for c in malos]
    assert not sucios, f"caracteres de control en archivos fuente: {sucios}"
