"""Cuota diaria sin identificar a nadie (servidor_indice/cuotas.py)."""

import json
from datetime import UTC, datetime

from servidor_indice.cuotas import Cuotas, Plan, cargar_claves, hash_clave, hoy, segundos_hasta_manana

MEDIODIA = datetime(2026, 9, 29, 17, 0, tzinfo=UTC)  # 12:00 en Colombia
MANANA = datetime(2026, 9, 30, 17, 0, tzinfo=UTC)


def test_la_ip_nunca_queda_en_memoria():
    """Regla 2 del proyecto: no se identifica a quien pregunta."""
    c = Cuotas(tope_ip=5)
    c.consumir("190.25.33.101", ahora=MEDIODIA)
    volcado = repr(c.estado_interno()) + repr(vars(c))
    assert "190.25.33.101" not in volcado


def test_la_sal_cambia_cada_dia_y_la_huella_de_ayer_no_se_puede_recalcular():
    c = Cuotas(tope_ip=5)
    c.consumir("190.25.33.101", ahora=MEDIODIA)
    huella_ayer = next(iter(c.estado_interno()["huellas"]))
    c.consumir("190.25.33.101", ahora=MANANA)
    huella_hoy = next(iter(c.estado_interno()["huellas"]))
    assert huella_ayer != huella_hoy
    assert c.estado_interno()["huellas"] == {huella_hoy: 1}  # el contador de ayer se borró


def test_tope_por_ip_y_renovacion_diaria():
    c = Cuotas(tope_ip=2)
    assert [c.consumir("1.2.3.4", ahora=MEDIODIA).permitido for _ in range(3)] == [True, True, False]
    assert c.consumir("5.6.7.8", ahora=MEDIODIA).permitido  # otra IP, otra cuenta
    assert c.consumir("1.2.3.4", ahora=MANANA).permitido


def test_clave_sin_tope():
    c = Cuotas(tope_ip=0, claves={hash_clave("k"): Plan("ilimitado", None)})
    assert all(c.consumir("1.1.1.1", "k", ahora=MEDIODIA).permitido for _ in range(100))


def test_cargar_claves_descarta_entradas_malas():
    h = hash_clave("buena")
    texto = (
        '{"' + h + '": {"nombre": "a", "tope_diario": 10}, "corta": {"tope_diario": 1}, '
        '"' + "0" * 64 + '": {"tope_diario": -3}}'
    )
    assert set(cargar_claves(texto)) == {h}
    assert cargar_claves("no es json") == {}


def test_el_dia_es_el_de_colombia():
    tarde_en_utc = datetime(2026, 9, 30, 3, 0, tzinfo=UTC)  # 22:00 del 29 en Colombia
    assert hoy(tarde_en_utc) == "2026-09-29"
    assert segundos_hasta_manana(tarde_en_utc) == 2 * 3600


# -- modelo freemium (29-sep-2026) --------------------------------------------

from datetime import date  # noqa: E402

from servidor_indice.cuotas import mensaje_bloqueo  # noqa: E402

FIN_DE_MES = datetime(2026, 9, 30, 17, 0, tzinfo=UTC)
MES_SIGUIENTE = datetime(2026, 10, 1, 17, 0, tzinfo=UTC)


def test_aporte_se_sugiere_pasado_el_tope_suave_sin_bloquear():
    c = Cuotas(tope_ip=30, tope_aporte=15)
    vs = [c.consumir("1.2.3.4", ahora=MEDIODIA) for _ in range(30)]
    assert all(v.permitido for v in vs)
    assert [v.sugerir_aporte for v in vs].index(True) == 15  # la consulta 16
    assert not c.consumir("1.2.3.4", ahora=MEDIODIA).permitido  # la 31


def test_plan_mensual_se_renueva_el_mes_siguiente_no_cada_dia():
    h = hash_clave("m")
    c = Cuotas(tope_ip=0, claves={h: Plan("mensual", 2, "mes", None)})
    assert [c.consumir("x", "m", ahora=MEDIODIA).permitido for _ in range(2)] == [True, True]
    assert not c.consumir("x", "m", ahora=FIN_DE_MES).permitido  # otro día, mismo mes
    assert c.consumir("x", "m", ahora=MES_SIGUIENTE).permitido


def test_clave_vencida_no_pasa_y_lo_dice():
    h = hash_clave("g")
    c = Cuotas(tope_ip=0, claves={h: Plan("gold", None, "dia", date(2026, 9, 29))})
    assert c.consumir("x", "g", ahora=MEDIODIA).permitido  # el día de vencimiento cuenta
    v = c.consumir("x", "g", ahora=MANANA)
    assert not v.permitido and v.vencida
    assert "venció" in mensaje_bloqueo(v)


def test_uso_de_claves_sobrevive_a_un_reinicio(tmp_path):
    ruta = str(tmp_path / "uso.json")
    claves = {hash_clave("m"): Plan("mensual", 2, "mes", None)}
    Cuotas(tope_ip=0, claves=claves, ruta_uso_claves=ruta).consumir("x", "m", ahora=MEDIODIA)
    Cuotas(tope_ip=0, claves=claves, ruta_uso_claves=ruta).consumir("x", "m", ahora=MEDIODIA)
    tercera = Cuotas(tope_ip=0, claves=claves, ruta_uso_claves=ruta).consumir("x", "m", ahora=MEDIODIA)
    assert not tercera.permitido
    assert "m" not in open(ruta, encoding="utf-8").read().replace('"mes"', "")  # la clave nunca en claro


def test_formato_viejo_tope_diario_se_sigue_aceptando():
    h = hash_clave("v")
    assert cargar_claves('{"' + h + '": {"nombre": "a", "tope_diario": 5}}')[h] == Plan("a", 5, "dia", None)


def test_gold_dura_pi_anios():
    import importlib.util

    spec = importlib.util.spec_from_file_location("crear", "scripts/crear_clave_api.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.DIAS_GOLD == 1147
    clave, entrada = m.emitir("gold", "Ana", desde=date(2026, 9, 29))
    (datos,) = entrada.values()
    assert datos["vence"] == "2029-11-19" and datos["tope"] is None
    assert clave not in json.dumps(entrada)  # solo el hash
    plan = cargar_claves(json.dumps(entrada))[hash_clave(clave)]
    assert plan.vence == date(2029, 11, 19)


def test_solo_se_ofrecen_planes_si_existen(monkeypatch):
    from servidor_indice.cuotas import Veredicto

    v = Veredicto(False, 30, 30, "ip")
    monkeypatch.delenv("ALIADO_PLANES_ACTIVOS", raising=False)
    assert "pase de un día" not in mensaje_bloqueo(v)
    monkeypatch.setenv("ALIADO_PLANES_ACTIVOS", "1")
    assert "pase de un día" in mensaje_bloqueo(v)
