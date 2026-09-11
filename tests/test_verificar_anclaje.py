"""Tests del verificador determinista de anclaje.

Medido contra las 150 respuestas reales ya juzgadas
(finetune/eval/resultados.json), no marca ni una sola respuesta buena: cero
falsos positivos. Ese es el requisito que estos tests protegen — NUNCA marcar
una respuesta buena, aunque cueste dejar pasar malas. Las cifras completas
están en docs/PROJECT_STATE.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from index.verificar_anclaje import marcar, verificar

FRAGMENTOS = [
    {
        "texto": (
            "DECRETO 1713 DE 2002. Artículo 40. La recolección y transporte de residuos "
            "originados por la poda de árboles se realizará mediante operativos especiales "
            "dentro de un plazo de treinta (30) días."
        ),
        "identificador_documento": "Decreto 1713 de 2002",
        "titulo_documento": "Decreto 1713 de 2002",
    },
    {
        "texto": "Ley 909 de 2004, artículo 24. El encargo no podrá ser superior a seis (6) meses.",
        "identificador_documento": "Ley 909 de 2004",
        "titulo_documento": "Ley 909 de 2004",
    },
]


def test_respuesta_fiel_queda_anclada():
    r = "Según el Decreto 1713 de 2002, artículo 40, se hace por operativos especiales en 30 días."
    assert verificar(r, FRAGMENTOS).anclada


def test_detecta_norma_inventada():
    """El fallo real que motivó el módulo: cita el Decreto 605 de 1996."""
    r = "Según el Decreto 605 de 1996, artículo 40, se hace por operativos especiales."
    informe = verificar(r, FRAGMENTOS)
    assert not informe.anclada
    assert any("605" in a.texto for a in informe.sin_respaldo)


def test_detecta_plazo_inventado():
    r = "Según el Decreto 1713 de 2002, el plazo es de 15 días."
    informe = verificar(r, FRAGMENTOS)
    assert not informe.anclada
    assert any("15" in a.texto for a in informe.sin_respaldo)


def test_detecta_articulo_inventado():
    r = "El Decreto 1713 de 2002, artículo 99, regula la poda."
    assert not verificar(r, FRAGMENTOS).anclada


def test_una_abstencion_cuenta_como_anclada():
    """No afirma nada verificable, así que no puede estar afirmando algo falso."""
    r = "No encontré información suficiente en el índice para responder esto con certeza."
    informe = verificar(r, FRAGMENTOS)
    assert informe.anclada
    assert informe.afirmaciones == []


def test_no_marca_por_diferencias_de_tildes_o_mayusculas():
    """El corpus escribe ARTÍCULO y el modelo articulo: eso no es una invención."""
    r = "Segun el decreto 1713 de 2002, ARTICULO 40, aplica el operativo especial."
    assert verificar(r, FRAGMENTOS).anclada


def test_numero_y_anio_deben_estar_juntos():
    """1713 en un sitio y 1996 en otro no constituyen una cita al Decreto 1713 de 1996."""
    r = "Según el Decreto 1713 de 1996 se hace por operativos especiales."
    assert not verificar(r, FRAGMENTOS).anclada


def test_reconoce_cantidades_escritas_con_digito_entre_parentesis():
    r = "El encargo no puede superar los 6 meses según la Ley 909 de 2004."
    assert verificar(r, FRAGMENTOS).anclada


def test_usa_tambien_la_metadata_no_solo_el_texto():
    frags = [{"texto": "El encargo dura seis meses.", "identificador_documento": "Ley 909 de 2004"}]
    assert verificar("Según la Ley 909 de 2004, dura seis meses.", frags).anclada


def test_marcar_señala_solo_lo_no_respaldado():
    r = "Según el Decreto 605 de 1996, artículo 40, aplica el operativo."
    informe = verificar(r, FRAGMENTOS)
    salida = marcar(r, informe)
    assert "Decreto 605 de 1996: no está en las fuentes citadas" in salida
    assert "artículo 40" in salida  # este sí estaba: no debe marcarse


def test_sin_fragmentos_todo_dato_queda_sin_respaldo():
    informe = verificar("Según la Ley 909 de 2004, son seis meses.", [])
    assert not informe.anclada


def test_frases_sin_respaldo_excluye_las_meta():
    r = "No encontré información en el índice. Según el Decreto 605 de 1996 son 15 días."
    informe = verificar(r, FRAGMENTOS)
    assert informe.frases_sin_respaldo
    assert all("No encontré" not in f for f in informe.frases_sin_respaldo)
