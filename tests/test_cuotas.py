"""Cuota diaria sin identificar a nadie (servidor_indice/cuotas.py)."""

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
