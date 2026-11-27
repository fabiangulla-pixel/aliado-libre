"""index/ubicar_citas.py: cada «cita» de la respuesta, en su posición exacta de la fuente."""

from index.ubicar_citas import ubicar

TEXTO = (
    "ARTÍCULO 64. Terminación unilateral del contrato sin justa causa. En todo contrato de trabajo va "
    "envuelta la condición resolutoria por incumplimiento de lo pactado, con indemnización de perjuicios a "
    "cargo de la parte responsable."
)
FRAGS = [{"id": "otro::frag0", "texto": "Nada que ver."}, {"id": "cst::frag3", "texto": TEXTO}]


def test_ubica_la_cita_en_el_texto_crudo():
    r = ubicar(
        "Revisa el art. 64: «En todo contrato de trabajo va envuelta la condición resolutoria».", FRAGS
    )
    assert len(r) == 1 and r[0]["n"] == 0
    (u,) = r[0]["ubicaciones"]
    assert u["id"] == "cst::frag3"
    assert TEXTO[u["inicio"] : u["fin"]] == "En todo contrato de trabajo va envuelta la condición resolutoria"


def test_ignora_tildes_mayusculas_y_espacios_pero_devuelve_posiciones_originales():
    r = ubicar("«en todo  CONTRATO de trabajo va envuelta la condicion resolutoria»", FRAGS)
    u = r[0]["ubicaciones"][0]
    assert TEXTO[u["inicio"] : u["fin"]] == "En todo contrato de trabajo va envuelta la condición resolutoria"


def test_cita_con_elision_se_ubica_por_trozos_en_orden():
    r = ubicar("«En todo contrato de trabajo va envuelta [...] a cargo de la parte responsable»", FRAGS)
    partes = r[0]["ubicaciones"]
    assert [TEXTO[p["inicio"] : p["fin"]] for p in partes] == [
        "En todo contrato de trabajo va envuelta",
        "a cargo de la parte responsable",
    ]


def test_cita_inventada_no_se_ubica():
    """Negativa: una paráfrasis entre comillas no apunta a ningún pasaje."""
    r = ubicar("«el empleador debe pagar siempre una indemnización completa»", FRAGS)
    assert r[0]["ubicaciones"] == []


def test_trozos_en_desorden_no_se_ubican():
    r = ubicar("«a cargo de la parte responsable [...] En todo contrato de trabajo va envuelta»", FRAGS)
    assert r[0]["ubicaciones"] == []


def test_varias_citas_numeradas_en_orden_y_sin_citas_lista_vacia():
    r = ubicar("«Terminación unilateral del contrato» y «condición resolutoria por incumplimiento»", FRAGS)
    assert [c["n"] for c in r] == [0, 1]
    assert ubicar("Sin comillas angulares.", FRAGS) == []
    assert ubicar("«corta»", FRAGS) == []  # menos de 15 caracteres: no cuenta como cita
