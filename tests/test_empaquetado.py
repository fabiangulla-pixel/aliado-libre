"""Pruebas del empaquetado con PyInstaller.

Dos cosas se verifican aquí:

1. Que la resolución de rutas de recursos funcione en modo congelado. En el
   .exe los datos se extraen a ``sys._MEIPASS`` y ``__file__`` ya no apunta a
   una carpeta real; si esto se rompe, el .exe arranca y devuelve 404 en todo.

2. Que la pila ML no haya quedado dentro del .exe. Buscar cadenas dentro del
   binario da FALSO NEGATIVO: el código va comprimido en un archivo PYZ, así
   que "torch" no aparece como texto plano aunque el módulo esté dentro. La
   única comprobación honesta es abrir el PYZ y listar sus módulos.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

import gui.server as servidor

RAIZ = Path(__file__).resolve().parent.parent
EXE = RAIZ / "dist" / "AliadoLibre.exe"

# Todo esto se queda fuera del .exe por diseño: el índice se consulta por HTTP
# contra el servidor remoto, no se calcula en la máquina del usuario.
PILA_PROHIBIDA = [
    "torch",
    "transformers",
    "sentence_transformers",
    "chromadb",
    "peft",
    "trl",
    "datasets",
    "accelerate",
    "scipy",
    "sklearn",
    "pandas",
    "safetensors",
    "huggingface_hub",
]


def test_raiz_recursos_usa_meipass_cuando_esta_congelado(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert servidor._raiz_recursos() == tmp_path


def test_raiz_recursos_es_el_repositorio_en_desarrollo(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert servidor._raiz_recursos() == RAIZ


def test_estatico_cuelga_de_la_raiz_de_recursos():
    # la ruta que sirve la página debe derivarse de la raíz de recursos, no de
    # __file__, para que valga igual congelado y sin congelar
    assert servidor.RAIZ_ESTATICA == servidor.RAIZ / "gui" / "static"
    assert (servidor.RAIZ_ESTATICA / "index.html").is_file()


def test_no_se_relanza_el_proceso_desde_el_codigo_empaquetado():
    """Regla dura: en un .exe congelado, relanzar ``sys.executable`` es una
    bomba fork (el .exe se ejecuta a sí mismo en bucle)."""
    for modulo in (RAIZ / "gui").rglob("*.py"):
        texto = modulo.read_text(encoding="utf-8")
        assert "sys.executable" not in texto, f"{modulo} relanza el proceso"


def _modulos_del_pyz() -> set[str]:
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

    archivo = CArchiveReader(str(EXE))
    destino = Path(tempfile.mkdtemp()) / "PYZ.pyz"
    destino.write_bytes(archivo.extract("PYZ.pyz"))
    return set(ZlibArchiveReader(str(destino)).toc)


@pytest.mark.skipif(not EXE.exists(), reason="no hay .exe compilado (corre scripts/build_exe.py)")
def test_el_pyz_del_exe_no_trae_la_pila_ml():
    raices = {modulo.split(".")[0] for modulo in _modulos_del_pyz()}
    coladas = sorted(raices & set(PILA_PROHIBIDA))
    assert not coladas, f"la pila ML se coló en el .exe: {coladas}"


@pytest.mark.skipif(not EXE.exists(), reason="no hay .exe compilado (corre scripts/build_exe.py)")
def test_el_pyz_del_exe_trae_lo_imprescindible():
    modulos = _modulos_del_pyz()
    assert "llama_cpp" in {m.split(".")[0] for m in modulos}
    assert "index.cliente_remoto" in modulos
    # Sin esto, el .exe falla con CERTIFICATE_VERIFY_FAILED en cualquier equipo
    # con un antivirus que inspeccione TLS. Ver confianza_tls.py.
    assert "confianza_tls" in modulos
    assert "truststore" in {m.split(".")[0] for m in modulos}
    # el índice local nunca debe viajar: importa lo que está excluido
    assert "index.buscar" not in modulos


# -- imagen del servidor del índice ---------------------------------------


def test_el_dockerfile_hornea_el_mismo_embedding_que_usa_el_buscador():
    """En runtime se fuerza HF_HUB_OFFLINE=1: lo que no quedó en la imagen ya
    no se puede descargar, y el servidor muere al arrancar. Al migrar a
    e5-large el Dockerfile se quedó con el modelo viejo y nada lo avisó."""
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "index/buscar.py" in dockerfile, (
        "El Dockerfile debe leer el nombre del modelo de index/buscar.py, "
        "no repetirlo a mano: dos copias se desincronizan en silencio."
    )
    buscar = (RAIZ / "index" / "buscar.py").read_text(encoding="utf-8")
    linea = next(línea for línea in buscar.splitlines() if línea.startswith("MODELO_EMBEDDINGS = "))
    modelo = linea.split('"')[-2]
    # Mismo sed que corre dentro del build: si deja de encontrar el nombre,
    # el `test -n "$MODELO"` del Dockerfile aborta la imagen. Aquí se detecta
    # antes, sin construir nada.
    import re

    patron = re.compile(r'^MODELO_EMBEDDINGS = os\.environ\.get\(".*", "(.*)"\)$', re.M)
    hallado = patron.search(buscar)
    assert hallado, "El sed del Dockerfile ya no casa con index/buscar.py"
    assert hallado.group(1) == modelo
