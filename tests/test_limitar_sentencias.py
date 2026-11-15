"""Tope de sentencias en el top-k: que las sentencias no copen la respuesta,
sin quitarle su sitio a la fuente que sí es la pertinente."""

from unittest.mock import patch

from index.buscar import IndiceBusqueda, limitar_sentencias


def _r(*ids):
    return [{"id": f"{i}::frag0"} for i in ids]


def _ids(res):
    return [r["id"].split("::")[0] for r in res]


def test_cinco_sentencias_dejan_sitio_a_las_normas():
    lista = _r(
        "corte_suprema:a",
        "corte_suprema:b",
        "corte_suprema:c",
        "corte_constitucional:d",
        "ley:1",
        "ley:2",
        "ley:3",
    )
    assert _ids(limitar_sentencias(lista, 5)) == [
        "corte_suprema:a",
        "corte_suprema:b",
        "ley:1",
        "ley:2",
        "ley:3",
    ]


def test_una_fuente_no_judicial_puede_llenar_todo():
    lista = _r("sic:1", "sic:2", "sic:3", "sic:4", "sic:5", "corte_suprema:a")
    assert _ids(limitar_sentencias(lista, 5)) == ["sic:1", "sic:2", "sic:3", "sic:4", "sic:5"]


def test_si_no_hay_otra_cosa_las_sentencias_vuelven_en_su_orden():
    lista = _r("corte_suprema:a", "consejo_estado:b", "corte_suprema:c", "ley:1", "corte_suprema:d")
    assert _ids(limitar_sentencias(lista, 5)) == [
        "corte_suprema:a",
        "consejo_estado:b",
        "ley:1",
        "corte_suprema:c",
        "corte_suprema:d",
    ]


def test_la_proporcion_escala_con_k():
    lista = _r(*[f"corte_suprema:{i}" for i in range(8)], *[f"ley:{i}" for i in range(8)])
    assert sum(i.startswith("corte") for i in _ids(limitar_sentencias(lista, 8))) == 3
    assert sum(i.startswith("corte") for i in _ids(limitar_sentencias(lista, 1))) == 1


def test_no_se_aplica_si_el_usuario_filtra_por_fuente():
    ix = IndiceBusqueda.__new__(IndiceBusqueda)
    todas = _r(*[f"corte_suprema:{i}" for i in range(6)])
    with (
        patch.object(IndiceBusqueda, "_buscar_crudo", return_value=todas),
        patch("index.reordenar.activo", return_value=True),
        patch("index.reordenar.reordenar", side_effect=lambda q, res, k=None: res[:k] if k else res),
        patch("index.vigencia.anotar", side_effect=lambda res: res),
    ):
        assert len(ix.buscar("x", k=5, fuentes=["corte_suprema"])) == 5
        assert sum(i.startswith("corte") for i in _ids(ix.buscar("x", k=5))) == 5  # sin otra cosa, vuelven
