"""Comprueba que las celdas de código de los notebooks al menos compilen.

Ruff excluye los `.ipynb` (están en `extend-exclude`), así que un notebook roto
pasa el lint, pasa los tests y solo falla en Colab — después de haber montado
Drive, instalado dependencias y cargado el modelo. Es decir, el error se
descubre en el sitio más caro posible y en la máquina de otra persona.

Este fallo ya ocurrió: una f-string partida por un salto de línea en la celda
final del análisis, con toda la parte cara del notebook por delante.

Compilar no garantiza que el notebook funcione. Garantiza que no se pierde una
sesión de GPU por un paréntesis.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
NOTEBOOKS = sorted(RAIZ.rglob("*.ipynb"))


def _codigo_python(fuente: str) -> str:
    """Quita las líneas mágicas de Jupyter (`!pip`, `%cd`), que no son Python."""
    return "\n".join(linea for linea in fuente.splitlines() if not linea.strip().startswith(("!", "%")))


def test_hay_notebooks_que_revisar():
    """Si el glob deja de encontrarlos, este archivo pasaría sin comprobar nada."""
    assert NOTEBOOKS, "no se encontró ningún .ipynb: ¿cambió la estructura del repo?"


@pytest.mark.parametrize("ruta", NOTEBOOKS, ids=lambda r: r.name)
def test_las_celdas_de_codigo_compilan(ruta: Path):
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    for numero, celda in enumerate(contenido.get("cells", [])):
        if celda.get("cell_type") != "code":
            continue
        codigo = _codigo_python("".join(celda.get("source", [])))
        if not codigo.strip():
            continue
        try:
            ast.parse(codigo)
        except SyntaxError as e:
            pytest.fail(f"{ruta.name}, celda {numero}: {e.msg} (línea {e.lineno})")
