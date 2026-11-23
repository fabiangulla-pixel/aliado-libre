"""La ficha de la Suprema llega al usuario: servidor (/api/buscar, /api/providencia,
filtros) y script de Ojeador (sin red). Providencias FICTICIAS: ver
tests/test_providencias.py."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

import gui.server as servidor_modulo
from gui.server import Handler
from index import providencias as P
from scripts import ojeador
from tests.test_providencias import corpus  # noqa: F401 (fixture)


@pytest.fixture()
def servidor():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _json(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


class _Indice:
    """Devuelve una providencia laboral, una civil y una norma."""

    def __init__(self):
        self.pedidos = []

    def buscar(self, consulta, k, fuentes=None):
        self.pedidos.append((k, fuentes))

        def r(id_, fuente, puntaje):
            return {"id": id_, "fuente": fuente, "texto": "x", "puntaje": puntaje}

        return [
            r("corte_suprema:laboral:SL99001-2026::frag0", "corte_suprema", 0.09),
            r("corte_suprema:civil:SC99003-2026::frag0", "corte_suprema", 0.05),
            r("legalize_co_github:LEY-1480-2011::frag1", "legalize_co_github", 0.04),
        ]


def test_buscar_trae_la_ficha_de_la_suprema_y_no_toca_lo_demas(servidor, corpus):  # noqa: F811
    with patch.object(servidor_modulo, "_obtener_indice", return_value=_Indice()):
        datos = _json(servidor + "/api/buscar?q=despido")
    fichas = [r.get("ficha", {}).get("numerador") for r in datos["resultados"]]
    assert fichas == ["SL99001-2026", "SC99003-2026", None]
    assert datos["filtros_providencia"] is None


def test_filtro_por_sala_limita_a_la_suprema_y_lo_dice(servidor, corpus):  # noqa: F811
    indice = _Indice()
    with patch.object(servidor_modulo, "_obtener_indice", return_value=indice):
        datos = _json(servidor + "/api/buscar?q=despido&sala=Laboral&anio_desde=2026")
    assert [r["ficha"]["numerador"] for r in datos["resultados"]] == ["SL99001-2026"]
    k, fuentes = indice.pedidos[0]
    assert fuentes == ["corte_suprema"] and k >= 30  # más candidatos, porque el filtro es posterior
    assert "puede haber más" in datos["filtros_providencia"]["nota"]
    assert datos["filtros_providencia"]["aplicados"] == {"sala": "Laboral", "anio_desde": 2026}


def test_filtros_invalidos_se_ignoran():
    assert (
        P.filtros_desde_parametros({"sala": ["Marciana"], "anio_desde": ["abc"], "tipo_providencia": ["x"]})
        == {}
    )


def test_filtro_por_anio_con_fecha_incompleta_usa_el_anio(corpus):  # noqa: F811
    r = P.anotar([{"id": "corte_suprema:laboral:SL99002-2026::frag0", "fuente": "corte_suprema"}])[0]
    assert P.cumple(r, {"anio_desde": 2026, "anio_hasta": 2026})
    assert not P.cumple(r, {"anio_hasta": 2025})
    assert not P.cumple({"id": "x"}, {"sala": "Laboral"})  # sin ficha no se sabe: no pasa


def test_api_providencia_devuelve_ficha_y_relaciones(servidor, corpus):  # noqa: F811
    datos = _json(servidor + "/api/providencia?id=corte_suprema:laboral:SL99001-2026")
    assert datos["ficha"]["numerador"] == "SL99001-2026"
    assert {c["identificador"] for c in datos["relaciones"]["cita_a"]} == {"SL99002-2026", "SL97777-2025"}


@pytest.mark.parametrize(
    "consulta, codigo",
    [("id=legalize_co_github:LEY-1480-2011", 400), ("id=", 400), ("id=corte_suprema:laboral:SL1-1999", 404)],
)
def test_api_providencia_rechaza_lo_que_no_es_de_la_suprema(servidor, corpus, consulta, codigo):  # noqa: F811
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(servidor + "/api/providencia?" + consulta)
    assert e.value.code == codigo


def test_api_providencia_sin_catalogo_lo_dice(servidor, monkeypatch):
    import importlib

    monkeypatch.setattr(P, "_cat", {})
    monkeypatch.setattr(importlib.import_module("index.providencias"), "_cat", {})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(servidor + "/api/providencia?id=corte_suprema:laboral:SL1-2020")
    assert e.value.code == 503


# --- script de Ojeador, sin red --------------------------------------------


def test_clasificar_resultados_de_ojeador():
    a = {"Numerador": "SL99001-2026", "Ubicacion": "X/SL99001-2026.docx", "Hash": "h1"}
    b = {
        "Numerador": "SL99001-2026",
        "Ubicacion": "X/SL99001-2026.docx",
        "Hash": "h2",
    }  # mismo archivo, dos filas
    c = {"Numerador": "SL99001-2026", "Ubicacion": "Y/otra.docx", "Hash": "h3"}
    otro = {"Numerador": "SL99001-2025", "Ubicacion": "Z"}
    assert ojeador.clasificar("SL99001-2026", [a, b])[0] == "verificada"
    assert ojeador.clasificar("SL99001-2026", [a, c]) == ("ambigua", None)
    assert ojeador.clasificar("SL99001-2026", [otro]) == ("no_encontrada", None)
    assert ojeador.clasificar("SL99001-2026", []) == ("no_encontrada", None)


def test_comparar_muestra_manual_csv(corpus, tmp_path):  # noqa: F811
    csv = tmp_path / "muestra.csv"
    csv.write_text(
        "Numerador;Sala;FechaConsolidacionFirma\n"
        "SL99001-2026;LABORAL;2026-03-09\n"  # está; la fecha no coincide con la del encabezado
        "SL99001-2026;LABORAL;2026-03-10\n"  # duplicado en la fuente
        "STL95555-2026;LABORAL;2026-05-01\n"  # no está
        "radicado 123;LABORAL;\n",  # no es un número de providencia
        encoding="utf-8",
    )
    i = ojeador.comparar(csv)
    assert i["identificadores_distintos"] == 2 and i["en_nuestro_catalogo"] == 1
    assert i["duplicados_en_la_fuente"] == {"SL99001-2026": 2}
    assert i["pendientes_de_comprobar"] == ["radicado 123"]
    assert {d["campo"] for d in i["discrepancias"]} == {"fecha"}
    assert (tmp_path / "muestra_cobertura.md").exists() and (tmp_path / "muestra_cobertura.json").exists()
    assert "No extrapolar" in (tmp_path / "muestra_cobertura.md").read_text(encoding="utf-8")


def test_intervalo_de_wilson():
    lo, hi = ojeador._wilson(9, 100)
    assert 0.04 < lo < 0.06 and 0.15 < hi < 0.17
    assert ojeador._wilson(0, 0) == (0.0, 0.0)
