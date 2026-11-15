"""OCR de la Corte Suprema: lo que garantiza que se pueda cortar en cualquier
momento (apagón, cierre de sesión) sin perder ni repetir sentencias."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / "scripts" / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


w = _cargar("ocr_cs_trabajador")
integrar = _cargar("ocr_cs_integrar")


def _fila(i):
    return {
        "id": f"corte_suprema:laboral:SL{i}-2019",
        "sala": "Laboral",
        "identificador": f"SL{i}-2019",
        "anio": "2019",
        "magistrado": "X",
        "ruta": f"/r/SL{i}-2019.pdf",
    }


def test_reparar_cola_corta_la_linea_a_medias_de_un_apagon(tmp_path):
    ruta = tmp_path / "r.jsonl"
    ruta.write_text('{"id": "a"}\n{"id": "b"}\n{"id": "c", "tex', encoding="utf-8")
    w.reparar_cola(ruta)
    assert ruta.read_text(encoding="utf-8") == '{"id": "a"}\n{"id": "b"}\n'
    w.reparar_cola(ruta)  # idempotente
    assert w.leer_ids(ruta) == {"a", "b"}


def test_reparar_cola_tolera_archivo_vacio_o_inexistente(tmp_path):
    w.reparar_cola(tmp_path / "no.jsonl")
    (tmp_path / "v.jsonl").write_text("", encoding="utf-8")
    w.reparar_cola(tmp_path / "v.jsonl")


def test_partes_son_disjuntas_y_cubren_todo():
    ids = [f"corte_suprema:laboral:SL{i}-2019" for i in range(500)]
    partes = [{i for i in ids if w.parte_de(i, 3) == p} for p in range(3)]
    assert set().union(*partes) == set(ids)
    assert sum(len(p) for p in partes) == len(ids)


def test_pendientes_salta_lo_resuelto_por_cualquier_parte(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "CARPETA", tmp_path)
    monkeypatch.setattr(w, "PENDIENTES", tmp_path / "pendientes.jsonl")
    filas = [_fila(i) for i in range(10)]
    (tmp_path / "pendientes.jsonl").write_text("\n".join(json.dumps(f) for f in filas), encoding="utf-8")
    w.anexar(tmp_path / "resultados_p1.jsonl", {"id": filas[0]["id"]})
    w.anexar(tmp_path / "fallidos_p0.jsonl", {"id": filas[1]["id"]})
    restantes = {f["id"] for p in range(2) for f in w.pendientes(p, 2)}
    assert restantes == {f["id"] for f in filas[2:]}


def test_si_falta_el_docx_baja_el_pdf():
    pedidos = []

    def falso(sesion, ruta):
        pedidos.append(ruta)
        if ruta.endswith(".docx"):
            raise w.FalloDefinitivo("no está")
        return b"%PDF"

    with patch.object(w, "descargar", side_effect=falso):
        assert w.bajar_alguna(None, "/a/SL1-2024.docx") == ("pdf", b"%PDF")
    assert pedidos == ["/a/SL1-2024.docx", "/a/SL1-2024.pdf"]


def test_doc_sin_hermanos_es_fallo_definitivo():
    with (
        patch.object(w, "descargar", side_effect=w.FalloDefinitivo("no")),
        pytest.raises(w.FalloDefinitivo, match=r"\.doc"),
    ):
        w.bajar_alguna(None, "/a/SL1-2019.doc")


def test_integrar_conserva_formato_y_marca_el_ocr():
    r = {**_fila(7), "texto": "x" * 200, "paginas": 30, "paginas_ocr": 28, "confianza": 0.99}
    d = integrar.a_documento(r)
    assert d.id == "corte_suprema:laboral:SL7-2019"
    assert d.fuente == "corte_suprema" and d.tipo == "sentencia"
    assert d.titulo == "Corte Suprema - Sala Laboral - Sentencia SL7-2019"
    assert d.metadata["ocr"] and d.metadata["confianza_ocr"] == 0.99
    assert integrar.a_documento({**r, "paginas_ocr": 0}).metadata["ocr"] is None
