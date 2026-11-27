"""index/plazos.py (festivos de Colombia, días hábiles) e index/liquidacion.py."""

from datetime import date

import pytest

from index import liquidacion as L
from index import plazos as P


def test_festivos_2026_coinciden_con_el_calendario_oficial():
    esperados = {
        "01-01", "12-01", "23-03", "02-04", "03-04", "01-05", "18-05", "08-06", "15-06", "29-06",
        "20-07", "07-08", "17-08", "12-10", "02-11", "16-11", "08-12", "25-12",
    }  # fmt: skip
    assert {d.strftime("%d-%m") for d in P.festivos(2026)} == esperados


def test_dos_festivos_el_mismo_lunes_no_se_pierden():
    """2025: San Pedro y San Pablo (29-jun, domingo) y Sagrado Corazón caen el 30 de junio."""
    nombre = P.festivos(2025)[date(2025, 6, 30)]
    assert "San Pedro" in nombre and "Sagrado Corazón" in nombre


def test_pascua_conocida():
    assert P.pascua(2026) == date(2026, 4, 5) and P.pascua(2025) == date(2025, 4, 20)


def test_vencimiento_salta_fines_de_semana_y_festivos():
    r = P.vencimiento(date(2026, 11, 27), 15)  # viernes; el 8-dic es festivo
    assert r["vence"] == "2026-12-21"
    assert [f["festivo"] for f in r["festivos_saltados"]] == ["Inmaculada Concepción"]
    # radicar un viernes: el día 1 es el lunes siguiente
    assert P.vencimiento(date(2026, 11, 27), 1)["vence"] == "2026-11-30"


@pytest.mark.parametrize("dias", [0, -1, 401])
def test_vencimiento_rechaza_terminos_absurdos(dias):
    with pytest.raises(ValueError):
        P.vencimiento(date(2026, 1, 1), dias)


def test_dias360():
    assert L.dias360(date(2026, 1, 1), date(2026, 12, 31)) == 360
    assert L.dias360(date(2026, 2, 1), date(2026, 2, 28)) == 30  # febrero completo cuenta 30
    assert L.dias360(date(2026, 7, 1), date(2026, 7, 31)) == 30
    assert L.dias360(date(2026, 5, 2), date(2026, 5, 1)) == 0


BASE = {
    "fecha_ingreso": "2024-03-01",
    "fecha_retiro": "2026-11-27",
    "salario": 2_000_000,
    "auxilio_transporte": 200_000,
    "vacaciones_disfrutadas": 15,
}


def _valor(r, concepto):
    return next(x["valor"] for x in r["lineas"] if x["concepto"].startswith(concepto))


def test_liquidacion_calculada_a_mano():
    r = L.calcular({**BASE, "motivo": "despido_sin_justa_causa"})
    assert _valor(r, "Cesantías") == round(2_200_000 * 327 / 360)  # 1-ene a 27-nov: 327 días
    assert _valor(r, "Intereses") == round(2_200_000 * 327 / 360 * 327 * 0.12 / 360)
    assert _valor(r, "Prima") == round(2_200_000 * 147 / 360)  # 1-jul a 27-nov
    assert _valor(r, "Vacaciones") == round((987 * 15 / 360 - 15) * 2_000_000 / 30)
    años = 987 / 360
    assert _valor(r, "Indemnización") == round((30 + (años - 1) * 20) * 2_000_000 / 30)
    assert r["total"] == sum(x["valor"] for x in r["lineas"])


def test_salario_alto_cambia_la_tabla_y_renuncia_no_indemniza():
    alto = L.calcular({**BASE, "motivo": "despido_sin_justa_causa", "salario_mayor_10_smmlv": True})
    años = 987 / 360
    assert _valor(alto, "Indemnización") == round((20 + (años - 1) * 15) * 2_000_000 / 30)
    renuncia = L.calcular({**BASE, "motivo": "renuncia"})
    assert not any(x["concepto"].startswith("Indemnización") for x in renuncia["lineas"])


def test_menos_de_un_año_indefinido_son_30_dias_y_obra_minimo_15():
    r = L.calcular({**BASE, "fecha_ingreso": "2026-09-01", "motivo": "despido_sin_justa_causa"})
    assert _valor(r, "Indemnización") == 2_000_000  # 30 días
    obra = L.calcular(
        {**BASE, "tipo_contrato": "obra", "motivo": "despido_sin_justa_causa", "dias_faltantes": 5}
    )
    assert _valor(obra, "Indemnización") == round(15 * 2_000_000 / 30)


def test_regimen_de_transicion_se_avisa_solo_a_quien_aplica():
    viejo = L.calcular({**BASE, "fecha_ingreso": "1990-01-15", "motivo": "despido_sin_justa_causa"})
    assert any("transición" in a for a in viejo["avisos"])
    nuevo = L.calcular({**BASE, "motivo": "despido_sin_justa_causa"})
    assert not any("transición" in a for a in nuevo["avisos"])


@pytest.mark.parametrize(
    "malo",
    [
        {**BASE, "fecha_retiro": "2020-01-01"},
        {**BASE, "salario": 0},
        {**BASE, "fecha_ingreso": "ayer"},
        {**BASE, "motivo": "inventado"},
    ],
)
def test_entradas_invalidas(malo):
    with pytest.raises(L.ErrorLiquidacion):
        L.calcular(malo)


def test_liquidacion_apagada_por_defecto(monkeypatch):
    monkeypatch.delenv("ALIADO_LIQUIDACION", raising=False)
    assert L.activa() is False
