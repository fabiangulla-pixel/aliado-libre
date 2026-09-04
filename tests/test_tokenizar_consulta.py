"""Tests del filtrado de la consulta antes de la búsqueda léxica.

Motivo medido: cada token se vuelve un término OR de FTS5 sobre 718.388
fragmentos. Una consulta de 73 palabras tardaba 15 s solo en la parte léxica, y
los perfiles que más escriben (adulto mayor, consulta con ruido) eran los más
castigados — es decir, el usuario menos experto pagaba la peor latencia.

Se prueba `_tokenizar` sin importar `index.buscar` entero, que arrastraría
torch y chromadb.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_modulo():
    class _Falso:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, _n):
            return _Falso()

        def __call__(self, *a, **k):
            return _Falso()

    originales = {n: sys.modules.get(n) for n in ("chromadb", "sentence_transformers")}
    sys.modules["chromadb"] = _Falso()
    sys.modules["sentence_transformers"] = _Falso()
    try:
        spec = importlib.util.spec_from_file_location("_buscar_tok", RAIZ / "index" / "buscar.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        for n, o in originales.items():
            if o is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = o
    return modulo


BUSCAR = _cargar_modulo()
_tokenizar = BUSCAR._tokenizar


def test_quita_palabras_vacias():
    tokens = _tokenizar("¿cual es el plazo para el encargo?")
    assert "plazo" in tokens and "encargo" in tokens
    assert "para" not in tokens and "cual" not in tokens


def test_quita_formulas_de_cortesia():
    """El perfil 'adulto mayor' envuelve la consulta en saludos."""
    tokens = _tokenizar("Buenas tardes, gracias, una pregunta sobre el encargo")
    assert tokens == ["encargo"]


def test_no_repite_tokens():
    tokens = _tokenizar("encargo encargo ENCARGO encárgo")
    assert tokens.count("encargo") == 1


def test_topa_el_numero_de_tokens():
    larga = " ".join(f"termino{i}" for i in range(40))
    assert len(_tokenizar(larga)) == BUSCAR.MAX_TOKENS_FTS


def test_consulta_solo_de_palabras_vacias_no_queda_vacia():
    """Preferible una búsqueda mala a ninguna búsqueda."""
    tokens = _tokenizar("que es lo que se puede hacer")
    assert tokens, "debería recurrir a los tokens crudos"


def test_normaliza_tildes():
    """El índice usa 'unicode61 remove_diacritics 2', así que indexa sin tildes."""
    assert _tokenizar("artículo") == _tokenizar("articulo")


def test_conserva_numeros_de_norma():
    """Lo más discriminante de una consulta jurídica no puede perderse."""
    assert _tokenizar("que dice la ley 909 de 2004 sobre el encargo") == [
        "ley",
        "909",
        "2004",
        "encargo",
    ]


def test_descarta_palabras_de_una_o_dos_letras():
    """Salvo que no quede nada: ahí se prefiere buscar mal a no buscar."""
    assert _tokenizar("el ok de la ue") == ["el", "ok", "de", "la", "ue"]
    assert _tokenizar("el ok de la ue en aduanas") == ["aduanas"]


def test_una_consulta_larga_se_reduce_mucho():
    """El caso real que motivó el cambio."""
    larga = (
        "Buenas tardes, mire que le cuento, mi sobrino trabaja en lo de aduanas y me dice "
        "que hay un fondo, entonces yo quisiera saber, por favor, quien es la persona que "
        "maneja la plata de ese fondo y si esa misma persona puede contratar empleados"
    )
    tokens = _tokenizar(larga)
    assert len(tokens) <= BUSCAR.MAX_TOKENS_FTS
    assert len(tokens) < len(larga.split()) / 2
    assert "aduanas" in tokens
