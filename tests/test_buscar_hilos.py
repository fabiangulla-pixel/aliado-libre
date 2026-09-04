"""Regresión: la conexión FTS5 no puede compartirse entre hilos.

El servidor de la GUI es un ThreadingHTTPServer, o sea un hilo por petición.
Con la conexión sqlite3 guardada en el objeto, la primera búsqueda funcionaba
y la segunda moría con "SQLite objects created in a thread can only be used in
that same thread" — un fallo que ninguna prueba de una sola consulta detecta.

No se carga el índice real (9 GB, torch, chromadb): se construye una instancia
sin pasar por __init__ y se le da un FTS5 de verdad, minúsculo, en tmp_path.
Lo que se prueba es exactamente la política de conexiones, que es donde estaba
el defecto.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_buscar_sin_dependencias(ruta_db: Path):
    """Importa index.buscar con chromadb y sentence_transformers falsos.

    Importarlo de verdad arrastraría torch: caro y ajeno a lo que se prueba.
    """

    class _Falso:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, _nombre):
            return _Falso()

        def __call__(self, *a, **k):
            return _Falso()

    modulos_falsos = {
        "chromadb": _Falso(),
        "sentence_transformers": _Falso(),
    }
    originales = {n: sys.modules.get(n) for n in modulos_falsos}
    sys.modules.update(modulos_falsos)
    try:
        spec = importlib.util.spec_from_file_location("_buscar_hilos", RAIZ / "index" / "buscar.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        for nombre, original in originales.items():
            if original is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = original
    modulo.DB_FTS = ruta_db
    return modulo


@pytest.fixture
def indice(tmp_path):
    ruta_db = tmp_path / "fts_index.db"
    con = sqlite3.connect(ruta_db)
    con.execute("CREATE VIRTUAL TABLE fragmentos_fts USING fts5(id, texto)")
    con.execute("INSERT INTO fragmentos_fts VALUES ('frag-1', 'encargo empleo de carrera')")
    con.commit()
    con.close()

    modulo = _cargar_buscar_sin_dependencias(ruta_db)
    obj = modulo.IndiceBusqueda.__new__(modulo.IndiceBusqueda)
    obj._local = threading.local()
    return obj


def _consultar(obj) -> list[str]:
    cursor = obj._fts.execute(
        "SELECT id FROM fragmentos_fts WHERE fragmentos_fts MATCH ? LIMIT 5", ('"encargo"',)
    )
    return [fila[0] for fila in cursor.fetchall()]


def test_consulta_desde_el_mismo_hilo_funciona(indice):
    assert _consultar(indice) == ["frag-1"]


def test_consulta_desde_otro_hilo_no_revienta(indice):
    """El caso real: la conexión se estrena en un hilo y se usa desde otro."""
    _consultar(indice)  # estrena la conexión en el hilo principal

    resultado: dict = {}

    def en_otro_hilo():
        try:
            resultado["ids"] = _consultar(indice)
        except Exception as e:  # noqa: BLE001 - se quiere ver cualquier fallo
            resultado["error"] = e

    hilo = threading.Thread(target=en_otro_hilo)
    hilo.start()
    hilo.join(timeout=10)

    assert "error" not in resultado, f"la conexión se compartió entre hilos: {resultado.get('error')}"
    assert resultado["ids"] == ["frag-1"]


def test_cada_hilo_recibe_su_propia_conexion(indice):
    conexiones = {}

    def registrar(nombre):
        conexiones[nombre] = indice._fts

    hilos = [threading.Thread(target=registrar, args=(f"h{i}",)) for i in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)

    objetos = list(conexiones.values())
    assert len(objetos) == 3
    assert len({id(c) for c in objetos}) == 3, "dos hilos compartieron la misma conexión"


def test_el_mismo_hilo_reusa_su_conexion(indice):
    """Abrir una conexión por consulta sería un derroche silencioso."""
    assert indice._fts is indice._fts
