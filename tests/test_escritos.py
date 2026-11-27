"""index/escritos.py: borradores sin IA, con blancos para lo que no se sabe."""

from datetime import date

import pytest

from index import escritos

HECHOS = "El 3 de noviembre me cortaron la luz sin aviso.\nYa pagué la factura de octubre."
FUENTE = "Artículo 140. El incumplimiento del contrato por parte del suscriptor da lugar a la suspensión."
FUND = {
    "titulo": "Ley 142 de 1994",
    "url": "https://www.funcionpublica.gov.co/x",
    "cita": "El incumplimiento del contrato por parte del suscriptor da lugar a la suspensión",
    "texto_fuente": FUENTE,
}


def test_borrador_completo_con_hechos_numerados_y_cita_literal():
    r = escritos.armar(
        {"tipo": "servicios", "hechos": HECHOS, "ciudad": "Bogotá", "fundamentos": [FUND]},
        hoy=date(2026, 11, 27),
    )
    t = r["texto"]
    assert t.startswith("Bogotá, 27 de noviembre de 2026")
    assert "1. El 3 de noviembre me cortaron la luz sin aviso." in t
    assert "2. Ya pagué la factura de octubre." in t
    assert (
        "Ley 142 de 1994 (texto oficial: https://www.funcionpublica.gov.co/x), que dispone: «El "
        "incumplimiento" in t
    )
    assert "Ley 142 de 1994, que en sus artículos 152" in t  # base legal fija
    assert not any("no coincide literalmente" in a for a in r["avisos"])


def test_lo_que_no_se_sabe_queda_en_blanco_y_no_se_inventa():
    t = escritos.armar({"tipo": "peticion", "hechos": HECHOS})["texto"]
    for blanco in (
        "[Tu nombre completo]",
        "cédula de ciudadanía n.º [__________]",
        "[Ciudad]",
        "Correo electrónico: [__________]",
    ):
        assert blanco in t
    assert "[Nombre de la entidad o empresa" in t


def test_cita_que_no_esta_en_la_fuente_se_avisa():
    malo = {**FUND, "cita": "La empresa nunca puede suspender el servicio"}
    r = escritos.armar({"tipo": "servicios", "hechos": HECHOS, "fundamentos": [malo]})
    assert any("no coincide literalmente" in a for a in r["avisos"])


def test_sin_fundamentos_se_avisa_y_tutela_lleva_juramento():
    r = escritos.armar({"tipo": "tutela", "hechos": HECHOS})
    assert any("No elegiste normas" in a for a in r["avisos"])
    assert "JURAMENTO" in r["texto"] and "Señores" not in r["texto"]
    assert any("perjuicio irremediable" in a for a in r["avisos"])


def test_peticiones_propias_reemplazan_las_de_plantilla_y_se_renumeran():
    t = escritos.armar(
        {
            "tipo": "consumidor",
            "hechos": HECHOS,
            "peticiones": "- Devolverme el dinero\n- Responder por escrito",
        }
    )["texto"]
    assert "1. Devolverme el dinero\n2. Responder por escrito" in t
    assert "[Escribe aquí qué pides" not in t


@pytest.mark.parametrize(
    "datos",
    [{"tipo": "demanda", "hechos": HECHOS}, {"tipo": "peticion", "hechos": "corto"}, {"tipo": "peticion"}],
)
def test_entradas_invalidas(datos):
    with pytest.raises(escritos.ErrorEscrito):
        escritos.armar(datos)


def test_caracteres_de_control_y_url_no_http_se_descartan():
    f = {**FUND, "url": "javascript:alert(1)"}
    t = escritos.armar({"tipo": "servicios", "hechos": HECHOS + "\x00\x07", "fundamentos": [f]})["texto"]
    assert "\x00" not in t and "javascript:" not in t
