import json
from pathlib import Path

from ingest.fuentes.corte_constitucional import _a_documento

FIXTURE = Path(__file__).parent / "fixtures" / "corte_constitucional_respuesta.json"


def _hits_fixture() -> list[dict]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["data"]["hits"]["hits"]


def test_a_documento_extrae_campos_reales():
    hits = _hits_fixture()
    documentos = [_a_documento(h) for h in hits]
    documentos = [d for d in documentos if d is not None]
    assert len(documentos) > 0

    doc = documentos[0]
    assert doc.fuente == "corte_constitucional"
    assert doc.tipo == "sentencia"
    assert doc.identificador  # algo tipo "T-534/20"
    assert len(doc.texto) > 20
    assert doc.url_original.startswith("https://www.corteconstitucional.gov.co/relatoria/")


def test_a_documento_conserva_metadata_relevante():
    hits = _hits_fixture()
    doc = next(d for d in (_a_documento(h) for h in hits) if d is not None)
    assert "tema" in doc.metadata
    assert "expediente" in doc.metadata
    assert isinstance(doc.metadata["magistrados"], list)


def test_a_documento_descarta_providencias_sin_sintesis():
    hit_vacio = {
        "_id": "999",
        "_source": {
            "prov_sentencia": "A.1/26",
            "prov_sintesis": "Sin información",
            "rutahtml": "Autos/2026/A1-26.htm",
        },
    }
    assert _a_documento(hit_vacio) is None


def test_a_documento_descarta_sin_sentencia():
    hit_sin_sentencia = {"_id": "1", "_source": {"prov_sintesis": "algo"}}
    assert _a_documento(hit_sin_sentencia) is None
