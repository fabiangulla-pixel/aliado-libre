"""¿Dónde está, en el texto de la fuente, cada cita literal de la respuesta?

La respuesta redactada cita entre «» y `index.respaldo` ya comprueba que esas
citas sean literales. Esto da un paso más, y es lo que el usuario ve: para cada
cita, en qué fragmento está y en qué posición EXACTA del texto crudo, para que
la página la resalte y salte a ella. Así «verifica la cita» deja de ser un
consejo y pasa a ser un clic.

Determinista y sin modelo. La comparación ignora tildes, mayúsculas, comillas
tipográficas y espacios repetidos (lo mismo que `respaldo.normalizar`), pero
las posiciones que devuelve son del texto ORIGINAL: un mapa de índices lleva
cada carácter normalizado a su carácter de origen. Una cita recortada con
puntos suspensivos se ubica por trozos, igual que se verifica.
"""

from __future__ import annotations

import re
import unicodedata

from index.respaldo import PATRON_CITA

MIN_TROZO = 15
_ELISION = re.compile(r"\[\s*\.\.\.\s*\]|\[…\]|\.\.\.|…")
_COMILLAS = {"“": '"', "”": '"', "«": '"', "»": '"', "’": "'", "‘": "'"}


def _normalizar_con_mapa(texto: str) -> tuple[str, list[int]]:
    """(texto normalizado, mapa) donde mapa[i] es la posición en `texto` del
    carácter normalizado i. Colapsa espacios y quita tildes como `respaldo`."""
    salida: list[str] = []
    mapa: list[int] = []
    previo_espacio = True  # quita los espacios iniciales
    for i, c in enumerate(texto):
        c = _COMILLAS.get(c, c)
        if c.isspace() or c == " ":
            if not previo_espacio:
                salida.append(" ")
                mapa.append(i)
            previo_espacio = True
            continue
        previo_espacio = False
        for d in unicodedata.normalize("NFKD", c):
            if unicodedata.combining(d):
                continue
            for e in d.lower():
                salida.append(e)
                mapa.append(i)
    while salida and salida[-1] == " ":
        salida.pop()
        mapa.pop()
    return "".join(salida), mapa


def _normalizar(texto: str) -> str:
    return _normalizar_con_mapa(texto)[0]


def trozos(cita: str) -> list[str]:
    return [t.strip() for t in _ELISION.split(cita) if len(t.strip()) >= MIN_TROZO]


def ubicar(respuesta: str, fragmentos: list[dict]) -> list[dict]:
    """Una entrada por cita entre «» de la respuesta, en orden de aparición:

    {"n": número de cita (0, 1, …), "cita": texto citado,
     "ubicaciones": [{"id": id del fragmento, "inicio": i, "fin": j}, …]}

    `ubicaciones` vacía = la cita no está literalmente en ningún fragmento (la
    misma condición por la que `respaldo` la marca). Cada trozo de una cita con
    elisión se ubica por separado y en orden dentro del MISMO fragmento.
    """
    citas = PATRON_CITA.findall(respuesta or "")
    if not citas:
        return []
    textos = []
    for f in fragmentos:
        if not isinstance(f, dict):
            continue
        norm, mapa = _normalizar_con_mapa(f.get("texto") or "")
        textos.append((str(f.get("id", "")), norm, mapa))

    salida = []
    for n, cita in enumerate(citas):
        partes = [_normalizar(t) for t in trozos(cita)]
        ubicaciones: list[dict] = []
        if partes:
            for fid, norm, mapa in textos:
                encontradas = []
                desde = 0
                for p in partes:
                    k = norm.find(p, desde)
                    if k < 0:
                        encontradas = []
                        break
                    encontradas.append({"id": fid, "inicio": mapa[k], "fin": mapa[k + len(p) - 1] + 1})
                    desde = k + len(p)
                if encontradas:
                    ubicaciones = encontradas
                    break
        salida.append({"n": n, "cita": cita, "ubicaciones": ubicaciones})
    return salida
