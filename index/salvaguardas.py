"""Salvaguardas deterministas sobre lo que un modelo propone para buscar.

El fallo medido de HyDE (12-sep-2026, recall@5 de 32,5% a 19,5%, p=0,0009): el
modelo inventa números de norma y FTS5, para quien un número de norma es el
término más discriminante del corpus, persigue la cita inventada. Pedirle al
modelo que no lo haga no basta; esto lo garantiza por código.

Origen: parche «árbol de consultas con poda» (27-sep-2026), del que solo esta
pieza se adoptó. Se usa en `index/busqueda_asistida.py` y servirá para el
traductor de consultas local.
"""

from __future__ import annotations

import re
import unicodedata

# "Ley 820 de 2003", "Decreto 1072", "T-025", "artículo 64", "2019"...
_NUMERO = re.compile(r"\b(?:[A-Za-z]{1,3}-)?\d[\d.]*\b")
# Lo que queda colgando al quitar el número: "ley de", "decreto", "artículo".
_COLGANTE = re.compile(
    r"\b(?:ley|decreto|resoluci[oó]n|art[ií]culo|art\.|sentencia|concepto|circular|acuerdo|"
    r"numeral|par[aá]grafo|inciso|literal)(?:\s+de)?\s*(?=$|[,;.]|\s(?:de\s)?(?:$|[,;.]))",
    flags=re.IGNORECASE,
)


def _sin_tildes(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _numeros(texto: str) -> set[str]:
    return {_sin_tildes(m.group()).rstrip(".") for m in _NUMERO.finditer(texto)}


def quitar_numeros_inventados(texto: str, original: str) -> str:
    """Borra de `texto` todo número (de norma, artículo, año, sentencia) que no
    esté en `original`. Los que el usuario sí escribió se respetan: son la mejor
    pista que hay."""
    permitidos = _numeros(original)

    def _filtrar(m: re.Match) -> str:
        return m.group() if _sin_tildes(m.group()).rstrip(".") in permitidos else ""

    limpio = _NUMERO.sub(_filtrar, texto)
    # dos pasadas: "Ley de" queda colgando tras borrar "820" y "2003"
    for _ in range(2):
        limpio = _COLGANTE.sub("", limpio)
    return re.sub(r"\s{2,}", " ", limpio).strip(" ,;.")
