"""De dónde sale la clave de Anthropic, y qué pasa cuando no está.

Los scripts de evaluación exigían la clave en el entorno, lo que obliga a
exportarla en cada terminal y termina con la clave pegada en el historial o en un
archivo del repositorio. El proyecto ya tenía dónde vive un secreto
(`~/.aliado_libre/credenciales.json`) y aquí se reutiliza.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from finetune import clave_api  # noqa: E402


@pytest.fixture()
def sin_entorno(monkeypatch):
    monkeypatch.delenv(clave_api.VARIABLE, raising=False)


def test_el_entorno_gana_sobre_el_archivo(monkeypatch, tmp_path):
    """Quien depura quiere que su variable mande sin borrar el archivo."""
    archivo = tmp_path / "credenciales.json"
    archivo.write_text(json.dumps({clave_api.CLAVE: "sk-del-archivo"}), encoding="utf-8")
    monkeypatch.setattr(clave_api, "ARCHIVO", archivo)
    monkeypatch.setenv(clave_api.VARIABLE, "sk-del-entorno")
    assert clave_api.leer_clave() == "sk-del-entorno"


def test_sin_entorno_se_lee_el_archivo(monkeypatch, tmp_path, sin_entorno):
    archivo = tmp_path / "credenciales.json"
    archivo.write_text(json.dumps({clave_api.CLAVE: "sk-del-archivo"}), encoding="utf-8")
    monkeypatch.setattr(clave_api, "ARCHIVO", archivo)
    assert clave_api.leer_clave() == "sk-del-archivo"


def test_una_variable_con_espacios_no_cuenta_como_clave(monkeypatch, tmp_path, sin_entorno):
    """`set ANTHROPIC_API_KEY=` deja la variable vacía, no ausente: si eso
    ganara, el archivo del usuario quedaría inalcanzable."""
    archivo = tmp_path / "credenciales.json"
    archivo.write_text(json.dumps({clave_api.CLAVE: "sk-del-archivo"}), encoding="utf-8")
    monkeypatch.setattr(clave_api, "ARCHIVO", archivo)
    monkeypatch.setenv(clave_api.VARIABLE, "   ")
    assert clave_api.leer_clave() == "sk-del-archivo"


@pytest.mark.parametrize(
    "contenido",
    ["{no es json", "[]", '{"otra_cosa": "x"}', '{"anthropic_api_key": ""}'],
)
def test_un_archivo_inservible_no_revienta(monkeypatch, tmp_path, sin_entorno, contenido):
    """Un JSON mal escrito debe dar el mensaje de ayuda, no un traceback."""
    archivo = tmp_path / "credenciales.json"
    archivo.write_text(contenido, encoding="utf-8")
    monkeypatch.setattr(clave_api, "ARCHIVO", archivo)
    assert clave_api.leer_clave(obligatoria=False) is None
    with pytest.raises(SystemExit) as exc:
        clave_api.leer_clave()
    assert "sk-ant-" in str(exc.value)  # el mensaje explica cómo arreglarlo


def test_sin_archivo_ni_entorno_explica_las_dos_formas(monkeypatch, tmp_path, sin_entorno):
    monkeypatch.setattr(clave_api, "ARCHIVO", tmp_path / "no-existe.json")
    with pytest.raises(SystemExit) as exc:
        clave_api.leer_clave()
    mensaje = str(exc.value)
    assert "credenciales.json" in mensaje
    assert clave_api.VARIABLE in mensaje


def test_la_clave_no_se_busca_en_el_repositorio():
    """Una clave dentro del repo está a un `git add` de GitHub."""
    assert clave_api.ARCHIVO.is_absolute()
    assert RAIZ not in clave_api.ARCHIVO.parents
    assert clave_api.ARCHIVO.parent.name == ".aliado_libre"
