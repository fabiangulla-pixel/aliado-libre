import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

from ingest.fuentes import corte_suprema as cs
from ingest.schema import Documento

TEXTO_LARGO = "Texto suficientemente largo. " * 10


def _docx(*parrafos: str) -> bytes:
    cuerpo = "".join(f'<w:p><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in parrafos)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body>{cuerpo}</w:body></w:document>")
    return buf.getvalue()


def _item(titulo: str, ruta: str | None = None) -> dict:
    return {"title": titulo, "onlinePath": ruta or f"/x/{titulo}", "doctor": "Dr. X", "ano": 2025}


def test_identificador_desde_titulo_extrae_radicado():
    assert cs._identificador_desde_titulo("SC2600-2026 [2026-01515-00].pdf") == "SC2600-2026"
    assert cs._identificador_desde_titulo("SL120-2025.pdf") == "SL120-2025"


def test_identificador_desde_titulo_sin_match_usa_nombre_sin_extension():
    assert cs._identificador_desde_titulo("algo_raro.pdf") == "algo_raro"


def test_es_sentencia_distingue_autos_y_tutelas():
    assert cs.es_sentencia("Laboral", "SL1747-2025.pdf")
    assert not cs.es_sentencia("Laboral", "AL472-2025.pdf")
    assert not cs.es_sentencia("Laboral", "STL12-2025.pdf")
    assert cs.es_sentencia("Civil", "SC1932-2025 [2015-0066].pdf")
    assert not cs.es_sentencia("Civil", "AC6541-2025.pdf")


def test_texto_docx_une_runs_y_desescapa():
    assert cs._texto_docx(_docx("CORTE SUPREMA", "Art. 64 &amp; s.")) == "CORTE SUPREMA\nArt. 64 & s."


def test_texto_completo_descarga_y_lee_docx():
    sesion = MagicMock()
    sesion.post.return_value.content = _docx("Hola", "mundo")
    assert cs._texto_completo(sesion, "/x/SL1-2025.docx") == "Hola\nmundo"
    assert sesion.post.call_args.kwargs["json"] == {"path": "/x/SL1-2025.docx"}


def test_texto_completo_none_con_doc_viejo_o_archivo_roto():
    sesion = MagicMock()
    assert cs._texto_completo(sesion, "/x/SL1-1999.doc") is None
    sesion.post.return_value.content = b"no es un zip"
    assert cs._texto_completo(sesion, "/x/SL1-2025.docx") is None


def test_listar_anio_prefiere_docx_y_filtra_autos():
    paginas = [
        [_item("SL1-2025.pdf"), _item("AL2-2025.pdf")],
        [_item("SL1-2025.docx"), _item("SL3-2025.pdf")],
        [],
    ]
    with patch.object(cs, "_buscar_pagina", side_effect=paginas), patch.object(cs.time, "sleep"):
        fallos = cs._listar_anio(MagicMock(), "Laboral", 2025, 0)
    assert {b: i["onlinePath"] for b, i in fallos.items()} == {
        "/x/SL1-2025": "/x/SL1-2025.docx",
        "/x/SL3-2025": "/x/SL3-2025.pdf",
    }


def test_crawl_reanuda_sin_redescargar_y_marca_anio_completo():
    previo = Documento(
        id="corte_suprema:laboral:SL1-2025",
        fuente="corte_suprema",
        tipo="sentencia",
        identificador="SL1-2025",
        titulo="t",
        fecha="2025",
        texto="previo",
        url_original="",
        metadata={"sala": "Laboral", "ruta": "/x/SL1-2025.pdf"},
    )
    listado = {"/x/SL1-2025": _item("SL1-2025.docx"), "/x/SL3-2025": _item("SL3-2025.pdf")}
    terminados = []
    with (
        patch.object(cs, "_listar_anio", return_value=listado),
        patch.object(cs, "_texto_completo", return_value=TEXTO_LARGO) as texto,
        patch.object(cs.time, "sleep"),
    ):
        docs = cs.crawl(
            max_documentos=10,
            pausa_segundos=0,
            documentos_previos=[previo],
            salas=["Laboral"],
            anios=[2025, 2024],
            anios_hechos={("Laboral", 2024)},
            al_terminar_anio=lambda s, a: terminados.append((s, a)),
        )
    assert [d.identificador for d in docs] == ["SL1-2025", "SL3-2025"]
    assert texto.call_count == 1
    assert docs[1].fecha == "2025"
    assert terminados == [("Laboral", 2025)]


def test_crawl_no_marca_anio_si_corta_por_tope():
    listado = {"/x/SL1-2025": _item("SL1-2025.pdf"), "/x/SL3-2025": _item("SL3-2025.pdf")}
    terminados = []
    with (
        patch.object(cs, "_listar_anio", return_value=listado),
        patch.object(cs, "_texto_completo", return_value=TEXTO_LARGO),
        patch.object(cs.time, "sleep"),
    ):
        docs = cs.crawl(
            max_documentos=1,
            pausa_segundos=0,
            salas=["Laboral"],
            anios=[2025],
            al_terminar_anio=lambda s, a: terminados.append((s, a)),
        )
    assert len(docs) == 1
    assert terminados == []


def test_crawl_descarta_textos_muy_cortos():
    with (
        patch.object(cs, "_listar_anio", return_value={"/x/SL1-2025": _item("SL1-2025.pdf")}),
        patch.object(cs, "_texto_completo", return_value="corto"),
        patch.object(cs.time, "sleep"),
    ):
        assert cs.crawl(max_documentos=10, pausa_segundos=0, salas=["Laboral"], anios=[2025]) == []
