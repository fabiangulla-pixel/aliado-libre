#!/usr/bin/env python3
"""Comprueba que el banco piloto no miente antes de medir nada con él.

Un banco de evaluación es una afirmación sobre el corpus, y si esa afirmación
es falsa toda medición que salga de él es basura. Aquí se verifica lo que se
puede verificar por programa, que es justo lo que evita tener que confiar en
quien lo escribió:

1. Cada `fragmento_id` anclado EXISTE en el índice.
2. Cada `cita_esperada` aparece LITERALMENTE en el texto de ese fragmento.
   Sin esto, una cita inventada al redactar el banco se volvería el patrón de
   oro contra el que se juzga a la aplicación.
3. Los casos `no_cubierto` NO tienen ancla (si la tuvieran, no serían casos de
   abstención).
4. Cada `documento_id` es el prefijo de su `fragmento_id`, que es como
   `medir_recuperacion.py` cuenta el acierto.

Uso:
    ./.venv/Scripts/python.exe finetune/eval/validar_banco_piloto.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
BANCO = RAIZ / "finetune" / "eval" / "banco_piloto_100.json"
DB_FTS = RAIZ / "index" / "fts_index.db"

TIPOS_CON_ANCLA = {"responde", "solo_referencia", "trampa_derogada"}
TIPOS_SIN_ANCLA = {"no_cubierto", "trampa_ambito"}


def normalizar(texto: str) -> str:
    """Compara ignorando espacios, comillas y acentos.

    El texto del corpus viene de OCR y de scraping: la misma frase aparece con
    comillas rectas o tipográficas, con espacios dobles o con un salto de línea
    en medio. Exigir igualdad byte a byte daría falsos fallos que esconderían
    los de verdad.
    """
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("“", '"').replace("”", '"')
    texto = texto.replace("‘", "'").replace("’", "'")
    texto = texto.replace("«", '"').replace("»", '"')
    texto = re.sub(r"[\s ]+", " ", texto)
    return texto.lower().strip()


def main() -> int:
    if not DB_FTS.exists():
        print(f"FALLO: no existe {DB_FTS}; no se puede validar contra el corpus.")
        return 1
    casos = json.loads(BANCO.read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{DB_FTS}?mode=ro", uri=True)

    errores: list[str] = []
    avisos: list[str] = []
    anclados = 0
    citas_ok = 0

    vistos: set[str] = set()
    for c in casos:
        cid = c["id"]
        if cid in vistos:
            errores.append(f"{cid}: id repetido")
        vistos.add(cid)

        tipo = c["tipo"]
        frag = c.get("fragmento_id")
        doc = c.get("documento_id")

        if tipo in TIPOS_SIN_ANCLA:
            if frag or doc:
                errores.append(f"{cid}: es '{tipo}' pero tiene ancla; no sería un caso de abstención")
            if c.get("cita_esperada"):
                errores.append(f"{cid}: es '{tipo}' y trae cita_esperada")
            continue

        if tipo not in TIPOS_CON_ANCLA:
            errores.append(f"{cid}: tipo desconocido {tipo!r}")
            continue

        if not frag:
            errores.append(f"{cid}: tipo '{tipo}' sin fragmento_id")
            continue

        if doc and not frag.startswith(doc):
            errores.append(
                f"{cid}: documento_id no es prefijo del fragmento_id "
                f"({doc!r} vs {frag!r}); el acierto por documento no cuadraría"
            )

        fila = con.execute("SELECT texto FROM fragmentos_fts WHERE id = ?", (frag,)).fetchone()
        if fila is None:
            errores.append(f"{cid}: el fragmento anclado NO existe en el índice: {frag}")
            continue
        anclados += 1

        cita = c.get("cita_esperada")
        if not cita:
            avisos.append(f"{cid}: anclado pero sin cita_esperada (no se podrá verificar la cita)")
            continue

        if normalizar(cita) in normalizar(fila[0]):
            citas_ok += 1
        else:
            errores.append(
                f"{cid}: la cita_esperada NO aparece literalmente en {frag}\n      esperada: {cita[:110]}..."
            )

    print("=" * 72)
    print(f"BANCO PILOTO: {len(casos)} casos")
    print("=" * 72)
    print("Por tipo   :", dict(Counter(c["tipo"] for c in casos)))
    print("Por perfil :", dict(Counter(c["perfil"] for c in casos)))
    print(f"\nAnclas verificadas en el índice : {anclados}")
    print(f"Citas verificadas literalmente  : {citas_ok}")

    if avisos:
        print(f"\nAvisos ({len(avisos)}):")
        for a in avisos:
            print("  -", a)

    if errores:
        print(f"\nERRORES ({len(errores)}):")
        for e in errores:
            print("  -", e)
        print("\nEl banco NO está listo: corregir antes de medir nada con él.")
        return 1

    print("\nBanco íntegro: todas las anclas existen y todas las citas son literales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
