from pathlib import Path

import pytest

from ingest.fuentes import legalize_co_github as lc

FIXTURES = Path(__file__).parent / "fixtures" / "legalize_co"


def test_parsear_archivo_extrae_front_matter_y_texto():
    doc = lc._parsear_archivo(FIXTURES / "LEY-1-1873.md")
    assert doc is not None
    assert doc.fuente == "legalize_co_github"
    assert doc.tipo == "ley"
    assert doc.identificador == "LEY-1-1873"
    assert doc.fecha == "1873-02-26"
    assert "Numeración" in doc.titulo or "numeraci" in doc.titulo.lower()
    assert len(doc.texto) > 40
    assert "---" not in doc.texto.split("\n")[0]


def test_parsear_archivo_none_sin_front_matter():
    doc = lc._parsear_archivo(FIXTURES / "sin_front_matter.md")
    assert doc is None


def test_crawl_lanza_si_no_existe_el_clon(tmp_path):
    with pytest.raises(FileNotFoundError):
        lc.crawl(raiz=tmp_path / "no_existe")


def test_crawl_lee_directorio_local(tmp_path):
    contenido = (FIXTURES / "LEY-1-1873.md").read_text(encoding="utf-8")
    (tmp_path / "LEY-1-1873.md").write_text(contenido, encoding="utf-8")
    docs = lc.crawl(raiz=tmp_path)
    assert len(docs) == 1
    assert docs[0].identificador == "LEY-1-1873"
