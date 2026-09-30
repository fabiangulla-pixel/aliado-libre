"""index/respaldo.py y el estado "condicional" del enrutador."""

from index.enrutador import decidir
from index.respaldo import citas_literales, respaldo_suficiente

FRAG = [
    {
        "id": "d::frag0",
        "texto": "El trabajador tendrá derecho a quince (15) días hábiles consecutivos de vacaciones.",
    }
]


def test_cita_literal_con_tildes_y_comillas_distintas():
    r = "Dice: «El trabajador tendrá derecho a quince (15) días hábiles consecutivos de vacaciones»."
    assert citas_literales(r, FRAG) == (1, 1)


def test_cita_recortada_con_puntos_suspensivos_es_literal():
    r = "«El trabajador tendrá derecho a quince (15) días … consecutivos de vacaciones»"
    assert citas_literales(r, FRAG) == (1, 1)


def test_respaldo_rechaza_abstencion_sin_cita_y_cita_falsa():
    assert not respaldo_suficiente("No encontré información suficiente en el índice.", FRAG)[0]
    assert not respaldo_suficiente("Tienes derecho a vacaciones pagadas.", FRAG)[0]
    assert not respaldo_suficiente("«El trabajador tendrá derecho a treinta días de vacaciones»", FRAG)[0]
    assert respaldo_suficiente("«tendrá derecho a quince (15) días hábiles consecutivos»", FRAG)[0]


def test_umbral_bajo_es_condicional_no_abstencion():
    d = decidir([{"id": "d::frag0", "texto": "x", "puntaje": 0.0167}], hay_clave_externa=True)
    assert d.motor == "condicional"
    assert d.puede_redactar and not d.responde  # la cobertura medida no cambia de sentido


def test_sin_resultados_sigue_siendo_abstencion():
    d = decidir([], hay_clave_externa=True)
    assert d.motor == "abstenerse" and not d.puede_redactar


def test_todo_no_vigente_se_abstiene_aunque_el_puntaje_sea_bajo():
    """La abstención por vigencia va ANTES del umbral: con coincidencia débil
    y todo derogado no se redacta nada."""
    derogada = {"estado": "derogada", "alcance": "documento", "nota": "Decreto derogado", "por": None}
    rs = [{"id": f"d::frag{i}", "texto": "x", "puntaje": 0.0167, "vigencia": derogada} for i in range(5)]
    assert decidir(rs, hay_clave_externa=True).motor == "abstenerse"
