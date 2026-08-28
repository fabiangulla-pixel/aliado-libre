import json
from pathlib import Path

from ingest.fuentes.supersociedades import _a_documento

FIXTURE = Path(__file__).parent / "fixtures" / "supersociedades_respuesta_es.json"


def _hit_fixture() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["hits"]["hits"][0]


def test_a_documento_extrae_texto_completo():
    doc = _a_documento(_hit_fixture())
    assert doc is not None
    assert doc.fuente == "supersociedades"
    assert doc.tipo == "concepto"
    assert "Inhabilidad" in doc.titulo
    assert len(doc.texto) > 100
    assert "ASUNTO" in doc.texto


def test_a_documento_extrae_descriptores_y_fuentes():
    doc = _a_documento(_hit_fixture())
    assert "Contrato" in doc.metadata["descriptores"]
    fuentes = doc.metadata["fuentes_juridicas"]
    assert any("222 de 1995" in f["fuente"] for f in fuentes)


def test_a_documento_devuelve_none_sin_contenido():
    hit_vacio = {
        "_id": "999",
        "_source": {
            "titulo": "vacío",
            "informacion": {},
            "documento_principal": {"contenido_archivo": ""},
            "descriptores": [],
            "fuentes_juridicas": [],
        },
    }
    assert _a_documento(hit_vacio) is None
