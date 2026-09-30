"""¿La respuesta está respaldada por los fragmentos que recibió?

Existe por la decisión del 29-sep-2026 sobre las abstenciones. El enrutador
callaba en 48 de las 100 consultas del piloto porque su umbral mide si los dos
motores coinciden, no si hay respuesta. Redactadas de todos modos, 21 de esas
48 daban una norma con citas literales verificadas; 9 citaban algo que no
estaba en el texto. Por debajo del umbral, la app ya no calla: redacta y solo
muestra la respuesta si pasa esta comprobación, que es determinista y la misma
que usa `finetune/eval/correr_piloto.py` para medir (una sola fuente de verdad:
si la app y la medición juzgaran distinto, la cifra no describiría la app).
"""

from __future__ import annotations

import re
import unicodedata

PATRON_CITA = re.compile(r"«([^»]{15,})»")
MARCAS_ABSTENCION = (
    "no encontré información suficiente",
    "no encontre informacion suficiente",
    "no está en el índice",
    "no esta en el indice",
    "no está indexad",
    "no esta indexad",
)


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    for a, b in (("“", '"'), ("”", '"'), ("«", '"'), ("»", '"'), ("’", "'"), ("‘", "'")):
        t = t.replace(a, b)
    return re.sub(r"[\s ]+", " ", t).lower().strip()


def citas_literales(respuesta: str, fragmentos: list[dict]) -> tuple[int, int]:
    """(citas entre «» que aparecen de verdad en los fragmentos, citas totales).

    Se comprueba contra los fragmentos que se le PASARON al modelo, no contra
    todo el corpus: citar bien algo que no estaba en el contexto seguiría
    siendo inventar. Una cita recortada con puntos suspensivos se verifica por
    trozos: elidir texto no es inventarlo.
    """
    contexto = normalizar(" ".join(f.get("texto", "") for f in fragmentos))
    citas = PATRON_CITA.findall(respuesta or "")
    if not citas:
        return 0, 0
    buenas = 0
    for c in citas:
        trozos = [
            t.strip()
            for t in re.split(r"\[\s*\.\.\.\s*\]|\[…\]|\.\.\.|…", normalizar(c))
            if len(t.strip()) >= 15
        ]
        if trozos and all(t in contexto for t in trozos):
            buenas += 1
    return buenas, len(citas)


def se_abstuvo(respuesta: str) -> bool:
    n = normalizar(respuesta or "")
    return any(normalizar(m) in n for m in MARCAS_ABSTENCION)


def respaldo_suficiente(respuesta: str, fragmentos: list[dict]) -> tuple[bool, str]:
    """Para respuestas redactadas con recuperación débil: se muestran solo si
    no son una abstención, traen al menos una cita y TODAS son literales.

    Devuelve (aceptada, motivo legible si se rechaza).
    """
    if se_abstuvo(respuesta):
        return False, "Los fragmentos encontrados no responden la consulta."
    buenas, total = citas_literales(respuesta, fragmentos)
    if total == 0:
        return False, "La respuesta no cita textualmente ninguna norma de las encontradas."
    if buenas < total:
        return False, (
            f"{total - buenas} de {total} citas de la respuesta no aparecen literalmente en las "
            "fuentes encontradas."
        )
    return True, ""
