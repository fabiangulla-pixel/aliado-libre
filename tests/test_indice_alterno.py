"""Rutas de indice por variable de entorno, y la guarda que impide mezclarlos."""

from __future__ import annotations

import importlib
import subprocess
import sys
import textwrap
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _en_subproceso(codigo: str, entorno: dict[str, str]) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, **entorno, "HF_HUB_OFFLINE": "1"}
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(codigo)],
        cwd=str(RAIZ),
        env=env,
        capture_output=True,
        text=True,
    )


def test_las_rutas_se_pueden_mover(tmp_path):
    destino = tmp_path / "chroma_alterno"
    res = _en_subproceso(
        """
        from index.buscar import DIR_INDICE, DB_FTS
        print(DIR_INDICE)
        print(DB_FTS)
        """,
        {"ALIADO_DIR_INDICE": str(destino)},
    )
    assert res.returncode == 0, res.stderr
    dir_indice, db_fts = res.stdout.strip().splitlines()
    assert Path(dir_indice) == destino.resolve()
    # El FTS se deriva al lado: nunca el Chroma de un indice con el FTS de otro.
    assert Path(db_fts).parent == destino.resolve().parent
    assert destino.name in Path(db_fts).name


def test_db_fts_sin_dir_indice_se_rechaza(tmp_path):
    """Prueba negativa: la guarda tiene que negarse de verdad, no solo existir."""
    res = _en_subproceso(
        "import index.buscar",
        {"ALIADO_DB_FTS": str(tmp_path / "suelto.db")},
    )
    assert res.returncode != 0
    assert "ALIADO_DB_FTS sin ALIADO_DIR_INDICE" in res.stderr


def test_sin_variables_apunta_al_indice_de_produccion():
    import index.buscar as buscar

    importlib.reload(buscar)
    assert buscar.DIR_INDICE == RAIZ / "index" / "chroma_db"
    assert buscar.DB_FTS == RAIZ / "index" / "fts_index.db"


class _ColeccionFalsa:
    def __init__(self, metadata=None, n=0):
        self.metadata = metadata
        self._n = n

    def count(self):
        return self._n

    def modify(self, metadata):
        self.metadata = metadata


def test_no_se_puede_reanudar_un_indice_del_otro_troceo(monkeypatch):
    import reindexar_con_gpu as r

    monkeypatch.setenv("ALIADO_TROCEO", "tamanio")
    coleccion = _ColeccionFalsa(metadata={"troceo": "parrafos"}, n=500_000)
    try:
        r.comprobar_troceo_compatible(coleccion)
    except SystemExit as e:
        assert "mezclado" in str(e)
    else:
        raise AssertionError("la guarda dejo pasar un indice del otro troceo")


def test_indice_poblado_sin_marca_tampoco_se_reanuda(monkeypatch):
    import reindexar_con_gpu as r

    monkeypatch.setenv("ALIADO_TROCEO", "tamanio")
    try:
        r.comprobar_troceo_compatible(_ColeccionFalsa(metadata=None, n=692_000))
    except SystemExit as e:
        assert "no dice con que troceo" in str(e)
    else:
        raise AssertionError("un indice sin marca y con datos deberia bloquear")


def test_indice_vacio_se_marca_y_pasa(monkeypatch):
    import reindexar_con_gpu as r

    monkeypatch.setenv("ALIADO_TROCEO", "tamanio")
    coleccion = _ColeccionFalsa(metadata=None, n=0)
    r.comprobar_troceo_compatible(coleccion)
    assert coleccion.metadata["troceo"] == "tamanio"


def _docs(n, largo=100):
    from ingest.schema import Documento

    return [
        Documento(
            id=f"doc{i}",
            fuente="gestor_normativo",
            tipo="ley",
            identificador=f"LEY {i}",
            titulo=f"Ley {i}",
            fecha="2020-01-01",
            texto="x" * largo,
            url_original=f"https://ejemplo.invalido/{i}",
        )
        for i in range(n)
    ]


def test_la_huella_del_corpus_es_estable_y_distingue_corpus():
    import reindexar_con_gpu as r

    a = _docs(10)
    assert r.huella_corpus(a) == r.huella_corpus(list(reversed(a)))  # el orden no cuenta
    assert r.huella_corpus(a) != r.huella_corpus(_docs(11))  # un documento mas, si
    assert r.huella_corpus(a) != r.huella_corpus(_docs(10, largo=101))  # mas texto, tambien


def test_no_se_puede_reanudar_un_indice_de_otro_corpus():
    """La guarda que no existia el 12-sep-2026, y por la que se comparo lo incomparable."""
    import reindexar_con_gpu as r

    coleccion = _ColeccionFalsa(metadata={"corpus": "deadbeefdeadbeef", "documentos": 100}, n=500)
    try:
        r.anotar_corpus(coleccion, _docs(10))
    except SystemExit as e:
        assert "no seria comparable" in str(e)
    else:
        raise AssertionError("la guarda dejo pasar un corpus distinto")


def test_el_mismo_corpus_se_reanuda_sin_estorbar():
    import reindexar_con_gpu as r

    docs = _docs(10)
    coleccion = _ColeccionFalsa(metadata=None, n=0)
    r.anotar_corpus(coleccion, docs)
    r.anotar_corpus(coleccion, docs)  # segunda pasada: no debe quejarse
    assert coleccion.metadata["documentos"] == 10
