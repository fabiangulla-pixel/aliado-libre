"""El enrutador de norma sube al puesto 1 la norma que dice el LLM, solo si la
búsqueda ya la trajo, y nunca rompe la búsqueda si el LLM falla."""

from index import enrutador_norma as E

DOCS = [
    {"documento_id": "dian:tributario:oficio_1", "titulo_documento": "Oficio sobre la Ley 1480 de 2011"},
    {"documento_id": "corte_constitucional:1", "titulo_documento": "Sentencia T-1/20"},
    {"documento_id": "legalize_co_github:LEY-1480-2011", "titulo_documento": "Estatuto del Consumidor"},
]


def test_sube_la_norma_sugerida_si_la_busqueda_la_trajo():
    orden, confianza = E.promover(DOCS, ("ley", 1480, "2011"))
    assert orden[0]["documento_id"] == "legalize_co_github:LEY-1480-2011"
    assert [r["documento_id"] for r in orden[1:]] == ["dian:tributario:oficio_1", "corte_constitucional:1"]
    assert confianza == "media"


def test_un_documento_que_solo_cita_la_norma_no_se_confunde_con_ella():
    orden, _ = E.promover(DOCS, ("ley", 1480, "2011"))
    assert orden[0]["documento_id"] != "dian:tributario:oficio_1"


def test_coincidencia_en_el_puesto_1_es_confianza_alta():
    orden, confianza = E.promover(DOCS[2:] + DOCS[:2], ("ley", 1480, "2011"))
    assert confianza == "alta"
    assert orden[0]["documento_id"] == "legalize_co_github:LEY-1480-2011"


def test_nunca_inyecta_lo_que_la_busqueda_no_trajo():
    orden, confianza = E.promover(DOCS, ("ley", 820, "2003"))
    assert orden == DOCS
    assert confianza == "baja"


def test_sin_sugerencia_no_toca_nada():
    assert E.promover(DOCS, None) == (DOCS, "baja")


def test_si_el_llm_no_responde_la_busqueda_sigue(monkeypatch):
    monkeypatch.setattr(E, "MODELO", "modelo-inexistente")
    monkeypatch.setattr(E, "URL", "http://127.0.0.1:9/api/chat")  # puerto cerrado
    monkeypatch.setattr(E, "TIEMPO", 2)
    assert E.norma_sugerida("me echaron del trabajo") is None


def test_apagado_por_defecto(monkeypatch):
    monkeypatch.setattr(E, "MODELO", "")
    assert not E.activo()
    assert E.norma_sugerida("me echaron del trabajo") is None


def test_afirma_solo_con_confianza_alta():
    alta = [{**DOCS[2], "confianza": "alta", "identificador_documento": "LEY-1480-2011"}] + DOCS[:2]
    af = E.afirmacion(alta)
    assert af["tipo"] == "afirma"
    assert af["titulo"] == "Estatuto del Consumidor"


def test_confianza_media_o_baja_presenta_opciones_sin_nombrar_norma():
    for conf in ("media", "baja"):
        af = E.afirmacion([{**DOCS[0], "confianza": conf}] + DOCS[1:])
        assert af == {"tipo": "opciones", "documento": None, "titulo": None}


def test_sin_enrutador_no_hay_afirmacion():
    assert E.afirmacion(DOCS) is None
    assert E.afirmacion([]) is None


def test_la_cita_exacta_antepuesta_no_hereda_la_afirmacion():
    # si otra cosa pasa al puesto 1, se afirma el documento marcado, no el primero
    marcado = {**DOCS[2], "confianza": "alta", "identificador_documento": "LEY-1480-2011"}
    af = E.afirmacion([{"titulo_documento": "Art. 64 CST", "cita_exacta": True}, marcado])
    assert af["documento"] == "LEY-1480-2011"
