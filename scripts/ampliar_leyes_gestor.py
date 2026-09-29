"""Trae del Gestor Normativo las leyes que le faltan al índice, año por año.

Por qué existe: el BFS de `ingest/fuentes/gestor_normativo.py` sigue enlaces de
vigencia y se cerró en 2.381 normas (hasta ~2019). Legalize-co tampoco trae las
leyes recientes. El 29-sep-2026 faltaban, entre otras, la Ley 1755 de 2015
(derecho de petición), la 2300 de 2023 (cobranzas), la 2101 de 2021 (jornada
laboral), la 2381 de 2024 (reforma pensional) y la 2466 de 2025 (reforma
laboral): lo que más pregunta la gente sobre trabajo y deudas.

El buscador del Gestor (`dafpIndexerBGN`) filtra por tipo y año y pagina de 10
en 10. Se listan las leyes de cada año, se descartan las que ya están en el
índice (por número y año, venga de la fuente que venga) y se descargan las
demás con el mismo parser del ingester. Checkpoint cada 20: las descargas son
lentas a propósito (una pausa por petición, es un servidor del Estado).

Uso:
    .venv/Scripts/python.exe scripts/ampliar_leyes_gestor.py --desde 2015 --listar
    .venv/Scripts/python.exe scripts/ampliar_leyes_gestor.py --desde 2015
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ingest.fuentes.gestor_normativo import _sesion, obtener_norma  # noqa: E402

BUSCADOR = "https://www.funcionpublica.gov.co/dafpIndexerBGN/norma/index"
RAW = RAIZ / "data" / "raw" / "gestor_normativo.json"
# Empieza por "_": cargar_documentos() de reindexar_con_gpu.py lo ignora.
DESCUBIERTAS = RAIZ / "data" / "raw" / "_leyes_gestor_descubiertas.json"
DB_FTS = RAIZ / "index" / "fts_index.db"

_RESULTADO = re.compile(
    r'norma\.php\?i=(?P<id>\d+)"[^>]*>\s*Ley\s+(?P<num>\d+)\s+de\s+(?P<anio>\d{4})\b',
    re.IGNORECASE,
)


def ley_por_numero(sesion, numero: int) -> tuple[str, str] | None:
    """(año, id del Gestor) de la Ley con ese número, o None.

    Se consulta por número y no por año: la paginación por año del buscador se
    corta sola (devolvía 37 leyes de 2023, cuando ese año hubo más de 80). Los
    números de ley son consecutivos, así que recorrerlos no deja huecos.
    """
    # (conexión, lectura): con un solo número, una respuesta que gotea no
    # dispara nunca el tope y el proceso se queda colgado sin error — pasó en
    # la primera corrida, parada en la ley 1750 sin una línea en el log.
    for intento in range(4):
        try:
            r = sesion.get(
                BUSCADOR,
                params={"find": "FindNext", "filtroTipoDocumento": "Ley", "filtroNumero": str(numero)},
                verify=False,
                timeout=(10, 20),
            )
            r.raise_for_status()
            break
        except Exception as e:  # red inestable del Estado: reintentar, no morir
            print(f"  ley {numero}: intento {intento + 1} falló ({type(e).__name__})", flush=True)
            time.sleep(5 * (intento + 1))
    else:
        return None
    for m in _RESULTADO.finditer(r.text):
        if m.group("num").lstrip("0") == str(numero):
            return m.group("anio"), m.group("id")
    return None


def leyes_en_indice() -> set[tuple[str, str]]:
    """Leyes presentes, por número y año, sin importar la fuente."""
    presentes: set[tuple[str, str]] = set()
    con = sqlite3.connect(f"file:{DB_FTS}?mode=ro", uri=True)
    patron = re.compile(r"(?:^|:)ley[-_](\d+)[-_](\d{4})$", re.IGNORECASE)
    for (fid,) in con.execute("SELECT id FROM fragmentos_fts"):
        if m := patron.search(fid.split("::", 1)[0]):
            presentes.add((m.group(1).lstrip("0"), m.group(2)))
    for d in json.loads(RAW.read_text(encoding="utf-8")):
        if m := re.match(r"Ley (\d+) de (\d{4})", d.get("titulo") or ""):
            presentes.add((m.group(1).lstrip("0"), m.group(2)))
    return presentes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # Ley 1735 es de enero de 2015; la 2560 cubre de sobra hasta 2026.
    ap.add_argument("--desde", type=int, default=1735, help="primer número de ley")
    ap.add_argument("--hasta", type=int, default=2560, help="último número de ley")
    ap.add_argument("--pausa", type=float, default=1.0)
    ap.add_argument("--listar", action="store_true", help="solo cuenta lo que falta; no descarga")
    a = ap.parse_args()

    sesion = _sesion()
    presentes = leyes_en_indice()
    faltan: list[tuple[str, str, str]] = []
    sin_gestor = 0
    cache: dict[str, list | None] = {}
    if DESCUBIERTAS.exists():
        cache = json.loads(DESCUBIERTAS.read_text(encoding="utf-8"))
    for numero in range(a.desde, a.hasta + 1):
        if str(numero) in cache:
            hallada = tuple(cache[str(numero)]) if cache[str(numero)] else None
        else:
            hallada = ley_por_numero(sesion, numero)
            cache[str(numero)] = list(hallada) if hallada else None
            time.sleep(a.pausa)
            if numero % 10 == 0:
                DESCUBIERTAS.write_text(json.dumps(cache), encoding="utf-8")
                print(f"  ley {numero} consultada", flush=True)
        if hallada is None:
            sin_gestor += 1
            continue
        anio, norma_id = hallada
        if (str(numero), anio) not in presentes:
            faltan.append((str(numero), anio, norma_id))
        if numero % 50 == 0:
            print(f"  ley {numero}: faltan {len(faltan)} hasta ahora")
    DESCUBIERTAS.write_text(json.dumps(cache), encoding="utf-8")
    print(f"{sin_gestor} números sin ley en el Gestor")
    print(f"Total que faltan: {len(faltan)}")
    if a.listar or not faltan:
        return 0

    documentos = json.loads(RAW.read_text(encoding="utf-8"))
    ya = {d["id"] for d in documentos}
    nuevos = 0
    for k, (num, anio, norma_id) in enumerate(faltan, 1):
        if f"gestor_normativo:{norma_id}" in ya:
            continue
        try:
            doc = obtener_norma(sesion, norma_id)
        except Exception as e:  # una ley que falla no tumba las demás
            print(f"  error: Ley {num} de {anio} (i={norma_id}): {type(e).__name__}", flush=True)
            doc = None
        time.sleep(a.pausa)
        if doc is None or len(doc.texto) < 200:
            print(f"  sin texto: Ley {num} de {anio} (i={norma_id})")
            continue
        documentos.append(doc.to_dict())
        nuevos += 1
        if nuevos % 20 == 0:
            RAW.write_text(json.dumps(documentos, ensure_ascii=False), encoding="utf-8")
            print(f"  checkpoint: {k}/{len(faltan)} ({nuevos} nuevas)")
    RAW.write_text(json.dumps(documentos, ensure_ascii=False), encoding="utf-8")
    print(f"{nuevos} leyes nuevas añadidas a {RAW.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
