"""index/relaciones_constitucional.py: citas entre providencias de la Corte Constitucional."""

import json

from index import relaciones_constitucional as rc


def test_canonica_y_referencias():
    assert rc.canonica_de_identificador("A. 024/92\xa0") == "A-024/92"
    assert rc.canonica_de_identificador("SU-214/16") == "SU-214/16"
    refs = [r[0] for r in rc.referencias("la sentencia T-760 de 2008, la C-355/06 y el Auto 004 de 2009")]
    assert refs == ["T-760/08", "C-355/06", "A-004/09"]


def test_no_confunde_expedientes_leyes_ni_prosa():
    """Negativa: nada de esto es una providencia de la Corte."""
    texto = "Expediente T-11756200. Ley 100 de 1993. Ver T 406 de 1992. Literal C 12 de 2005. T-500/45."
    assert rc.referencias(texto) == []


def test_construir_y_consultar(tmp_path):
    crudo = [
        {
            "id": "corte_constitucional:1",
            "identificador": "T-760/08",
            "fecha": "2008-07-31",
            "texto": "Salud.",
            "url_original": "u1",
        },
        {
            "id": "corte_constitucional:2",
            "identificador": "T-100/20",
            "fecha": "2020-01-01",
            "texto": (
                "Sentencia T-100/20. Como dijo la sentencia T-760 de 2008, y reiteró la T-760/08, "
                "y la C-999/99."
            ),
            "url_original": "u2",
        },
    ]
    ruta_raw = tmp_path / "cc.json"
    ruta_raw.write_text(json.dumps(crudo), encoding="utf-8")
    db = tmp_path / "rel.db"
    resumen = rc.construir([ruta_raw], db)
    assert resumen["relaciones"] == 2 and resumen["confirmadas"] == 1 and resumen["no_resueltas"] == 1

    sale = rc.relaciones("corte_constitucional:2", ruta=db)
    assert {c["identificador"] for c in sale["cita_a"]} == {"T-760/08", "C-999/99"}
    t760 = next(c for c in sale["cita_a"] if c["identificador"] == "T-760/08")
    assert t760["veces"] == 2 and t760["estado"] == "confirmada"
    assert all(c["identificador"] != "T-100/20" for c in sale["cita_a"])  # no se cita a sí misma

    entra = rc.relaciones("corte_constitucional:1", ruta=db)
    assert entra["total_citada_por"] == 1 and entra["citada_por"][0]["identificador"] == "T-100/20"
    assert entra["providencia"]["identificador"] == "T-760/08"
    assert rc.relaciones("corte_constitucional:999", ruta=db) is None
