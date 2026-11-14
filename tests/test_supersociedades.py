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


def _hit(i: str) -> dict:
    return {
        "_id": i,
        "_source": {
            "titulo": f"T{i}",
            "informacion": {},
            "documento_principal": {"contenido_archivo": "x" * 200},
        },
    }


def test_crawl_pagina_con_search_after_y_conserva_previos(monkeypatch):
    from ingest.fuentes import supersociedades as ss
    from ingest.schema import Documento

    paginas = {None: [_hit("a"), _hit("b")], "b": [_hit("c")], "c": []}
    pedidos = []

    def falso_query(despues_de, tamanio):
        pedidos.append(despues_de)
        return {"hits": {"hits": paginas[despues_de]}}

    monkeypatch.setattr(ss, "_query", falso_query)
    previo = Documento(
        id="supersociedades:a",
        fuente="supersociedades",
        tipo="concepto",
        identificador="a",
        titulo="ya anonimizado",
        fecha=None,
        texto="[DESTINATARIO]",
        url_original="",
        metadata={},
    )
    docs = ss.crawl(max_documentos=100, pausa_segundos=0, documentos_previos=[previo])

    assert pedidos == [None, "b", "c"]
    assert [d.id for d in docs] == ["supersociedades:a", "supersociedades:b", "supersociedades:c"]
    assert docs[0].texto == "[DESTINATARIO]"


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
