from unittest.mock import MagicMock, patch

from ingest.fuentes import corte_suprema as cs


def test_identificador_desde_titulo_extrae_radicado():
    assert cs._identificador_desde_titulo("AC2600-2026 [2026-01515-00].pdf") == "AC2600-2026"


def test_identificador_desde_titulo_sin_match_usa_nombre_sin_extension():
    assert cs._identificador_desde_titulo("algo_raro.pdf") == "algo_raro"


def test_texto_completo_limpia_html_y_marcas():
    respuesta = {"getContentSearch": {"contentText": "<p>Hola <mark>mundo</mark></p>"}}
    with patch("ingest.fuentes.corte_suprema._graphql", return_value=respuesta):
        texto = cs._texto_completo(MagicMock(), "/ruta/doc.pdf", "Civil")
    assert texto == "Hola\nmundo"


def test_texto_completo_none_si_falla_graphql():
    with patch("ingest.fuentes.corte_suprema._graphql", side_effect=RuntimeError("502")):
        texto = cs._texto_completo(MagicMock(), "/ruta/doc.pdf", "Civil")
    assert texto is None


def test_crawl_dedupe_pdf_y_docx_del_mismo_documento():
    resultados_pagina_1 = [
        {"title": "AC1-2026.pdf", "onlinePath": "/x/AC1-2026.pdf", "doctor": "Dr. X"},
        {"title": "AC1-2026.docx", "onlinePath": "/x/AC1-2026.docx", "doctor": "Dr. X"},
    ]
    texto_largo = "Texto suficientemente largo. " * 10
    with (
        patch(
            "ingest.fuentes.corte_suprema._buscar_pagina",
            side_effect=[resultados_pagina_1, [], [], [], []],
        ),
        patch("ingest.fuentes.corte_suprema._texto_completo", return_value=texto_largo),
        patch("ingest.fuentes.corte_suprema.time.sleep"),
    ):
        docs = cs.crawl(max_documentos=10, pausa_segundos=0)
    assert len(docs) == 1
    assert docs[0].metadata["sala"] == "Civil"


def test_crawl_descarta_textos_muy_cortos():
    resultados = [{"title": "AC1-2026.pdf", "onlinePath": "/x/AC1-2026.pdf", "doctor": "Dr. X"}]
    with (
        patch("ingest.fuentes.corte_suprema._buscar_pagina", side_effect=[resultados, [], [], [], []]),
        patch("ingest.fuentes.corte_suprema._texto_completo", return_value="corto"),
        patch("ingest.fuentes.corte_suprema.time.sleep"),
    ):
        docs = cs.crawl(max_documentos=10, pausa_segundos=0)
    assert docs == []


def test_crawl_reanuda_sin_repetir_ruta_ya_vista():
    from ingest.schema import Documento

    previo = Documento(
        id="corte_suprema:civil:AC1-2026",
        fuente="corte_suprema",
        tipo="sentencia",
        identificador="AC1-2026",
        titulo="Corte Suprema - Sala Civil - AC1-2026.pdf",
        fecha=None,
        texto="texto previo",
        url_original="https://x",
        metadata={"sala": "Civil", "magistrado": "Dr. X", "ruta": "/x/AC1-2026.pdf"},
    )
    resultados_pagina = [
        {"title": "AC1-2026.pdf", "onlinePath": "/x/AC1-2026.pdf", "doctor": "Dr. X"},  # ya visto
        {"title": "AC2-2026.pdf", "onlinePath": "/x/AC2-2026.pdf", "doctor": "Dr. Y"},  # nuevo
    ]
    texto_largo = "Texto suficientemente largo. " * 10
    with (
        patch("ingest.fuentes.corte_suprema._buscar_pagina", side_effect=[resultados_pagina, [], [], [], []]),
        patch("ingest.fuentes.corte_suprema._texto_completo", return_value=texto_largo) as mock_texto,
        patch("ingest.fuentes.corte_suprema.time.sleep"),
    ):
        docs = cs.crawl(max_documentos=10, pausa_segundos=0, documentos_previos=[previo])
    identificadores = {d.identificador for d in docs}
    assert identificadores == {"AC1-2026", "AC2-2026"}
    # solo se pidió texto completo para el documento nuevo, no para el ya visto
    assert mock_texto.call_count == 1
    assert mock_texto.call_args[0][1] == "/x/AC2-2026.pdf"
