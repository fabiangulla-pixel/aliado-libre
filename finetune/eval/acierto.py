"""Cuando un resultado cuenta como acierto. Dos medidas, siempre reportadas juntas.

- `exacto`: el documento que se anoto al escribir la pregunta (la de siempre).
- `equivalente`: ademas, la MISMA norma guardada en otra fuente. El Estatuto del
  Consumidor esta en legalize_co y en la DIAN; el Codigo Sustantivo del Trabajo,
  en legalize_co y en el Gestor Normativo. La medida exacta contaba como fallo
  traer la ley correcta desde la otra fuente: el 20-nov-2026, sobre el piloto,
  13 de 95 casos tenian la norma correcta entre los 60 candidatos y no contaban.

La norma esperada sale del id del documento anclado o de `norma_esperada` del
caso (la que cita la respuesta de referencia). Solo leyes, decretos,
resoluciones, actos legislativos y circulares: una sentencia o un concepto no
tiene "otra copia" reconocible por numero, asi que para ellos solo vale el exacto.
"""

from __future__ import annotations

from index.normas import norma, norma_de_resultado  # una sola definicion con el programa

__all__ = [
    "norma",
    "norma_de_resultado",
    "normas_esperadas",
    "norma_esperada",
    "es_exacto",
    "es_equivalente",
    "posicion",
]


def normas_esperadas(caso: dict) -> set[tuple[str, int, str]]:
    """La del documento anclado y la que cita la respuesta de referencia.

    Pueden diferir: "licencia de conduccion" esta anclada a la Ley 33 de 1986
    porque era lo que habia en el indice, y la referencia dice "Ley 769 de 2002
    (Codigo vigente)". Traer la vigente no es un fallo."""
    doc = caso.get("documento_id", "")
    return {
        n for n in (norma(doc.split(":", 1)[-1].replace("_", "-")), norma(caso.get("norma_esperada"))) if n
    }


def norma_esperada(caso: dict) -> tuple[str, int, str] | None:
    doc = caso.get("documento_id", "")
    return norma(doc.split(":", 1)[-1].replace("_", "-")) or norma(caso.get("norma_esperada"))


def es_exacto(r: dict, caso: dict) -> bool:
    return r.get("documento_id") == caso.get("documento_id")


def es_equivalente(r: dict, caso: dict) -> bool:
    if es_exacto(r, caso):
        return True
    # `aceptables`: otros documentos que una persona (Fabian) reviso y juzgo
    # que tambien responden la pregunta. Solo humanos los anaden: un juicio de
    # IA no es verdad de referencia.
    if r.get("documento_id") in caso.get("aceptables", ()):
        return True
    obtenida = norma_de_resultado(r)
    return obtenida is not None and obtenida in normas_esperadas(caso)


def posicion(resultados: list[dict], caso: dict, equivalente: bool = False) -> int | None:
    """Indice (0 = primero) del primer acierto, o None."""
    prueba = es_equivalente if equivalente else es_exacto
    for i, r in enumerate(resultados):
        if prueba(r, caso):
            return i
    return None
