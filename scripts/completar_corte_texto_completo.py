"""Trae el texto completo de las sentencias de la Corte Constitucional que no tienen síntesis.

Por qué existe: `ingest/fuentes/corte_constitucional.py` indexa la síntesis
(`prov_sintesis`) y descarta las providencias que no la traen. El 6-oct-2026 eso
eran 10.346 de las 29.474 del registro oficial (datos.gov.co v2k4-2t8s), casi
todas de 1992-2004: en 1995 faltaban 622 de 692. El buscador sí da la ruta del
HTML de cada una (`rutahtml`), y ahí está el texto completo.

Los documentos se guardan en `data/raw/corte_constitucional_texto.json` con el
mismo id que usaría el ingester (`corte_constitucional:<_id>`), así que no
chocan con los que ya están: son exactamente los que el ingester descartó.
Después se indexan con `reindexar_con_gpu.py --ampliar`.

Checkpoint cada 50 sentencias; al relanzar no se vuelve a descargar lo hecho.
Una pausa por petición: es un servidor del Estado.

Uso:
    .venv/Scripts/python.exe scripts/completar_corte_texto_completo.py --listar
    .venv/Scripts/python.exe scripts/completar_corte_texto_completo.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ingest.fuentes.corte_constitucional import HEADERS, _buscar_por_anio  # noqa: E402
from ingest.normalizar import fix_mojibake  # noqa: E402
from ingest.schema import Documento  # noqa: E402

SALIDA = RAIZ / "data" / "raw" / "corte_constitucional_texto.json"
BASE_HTML = "https://www.corteconstitucional.gov.co/relatoria/"
MINIMO_CARACTERES = 500  # menos que esto es una página de error, no una sentencia


def sin_sintesis(hit: dict) -> bool:
    return (hit["_source"].get("prov_sintesis") or "").strip() in ("", "Sin información")


def texto_de_html(contenido: bytes) -> str:
    # Las relatorías antiguas declaran ISO-8859-1 pero son Windows-1252 (comillas, guiones).
    html = contenido.decode("windows-1252", errors="replace")
    sopa = BeautifulSoup(html, "lxml")
    for etiqueta in sopa(["script", "style"]):
        etiqueta.decompose()
    texto = sopa.get_text("\n")
    # Word parte las líneas a mitad de frase: se unen, y se conservan los párrafos.
    texto = re.sub(r"[ \t\xa0]+", " ", texto)
    texto = re.sub(r" ?\n ?", "\n", texto)
    texto = re.sub(r"(?<!\n)\n(?!\n)", " ", texto)
    texto = re.sub(r"\n{2,}", "\n\n", texto)
    return fix_mojibake(texto.strip())


def a_documento(hit: dict, texto: str) -> Documento:
    src = hit["_source"]
    sentencia = src["prov_sentencia"]
    return Documento(
        id=f"corte_constitucional:{hit['_id']}",
        fuente="corte_constitucional",
        tipo="sentencia",
        identificador=sentencia,
        titulo=f"Sentencia {sentencia} - Corte Constitucional",
        fecha=src.get("prov_f_sentencia"),
        texto=texto,
        url_original=BASE_HTML + src["rutahtml"],
        metadata={
            "tema": src.get("prov_tema"),
            "tipo_providencia": src.get("prov_tipo"),
            "expediente": src.get("prov_expediente"),
            "magistrados": src.get("prov_magistrados") or [],
            "sala": src.get("sala_seguimiento"),
            "contenido": "texto_completo",
        },
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desde", type=int, default=1992)
    p.add_argument("--hasta", type=int, default=date.today().year)
    p.add_argument("--pausa", type=float, default=0.7)
    p.add_argument("--listar", action="store_true", help="solo contar por año, sin descargar")
    a = p.parse_args()

    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    hechos: dict[str, dict] = {}
    if SALIDA.exists():
        hechos = {d["id"]: d for d in json.loads(SALIDA.read_text(encoding="utf-8"))}
        print(f"{len(hechos)} ya descargadas: no se repiten")

    def guardar() -> None:
        tmp = SALIDA.with_suffix(".tmp")
        tmp.write_text(json.dumps(list(hechos.values()), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(SALIDA)

    fallos: list[str] = []
    nuevos = 0
    for anio in range(a.desde, a.hasta + 1):
        hits = [h for h in _buscar_por_anio(sesion, anio) if h["_source"].get("prov_sentencia")]
        faltan = [h for h in hits if sin_sintesis(h) and h["_source"].get("rutahtml")]
        pendientes = [h for h in faltan if f"corte_constitucional:{h['_id']}" not in hechos]
        print(
            f"{anio}: {len(hits)} providencias, {len(faltan)} sin síntesis, {len(pendientes)} pendientes",
            flush=True,
        )
        if a.listar:
            continue
        for h in pendientes:
            ruta = h["_source"]["rutahtml"]
            try:
                r = sesion.get(BASE_HTML + ruta, verify=False, timeout=60)
                r.raise_for_status()
                texto = texto_de_html(r.content)
            except Exception as e:  # noqa: BLE001 - se anota y se sigue; al relanzar se reintenta
                fallos.append(f"{ruta}: {e}")
                time.sleep(a.pausa * 5)
                continue
            if len(texto) < MINIMO_CARACTERES:
                fallos.append(f"{ruta}: solo {len(texto)} caracteres")
            else:
                doc = a_documento(h, texto)
                hechos[doc.id] = doc.to_dict()
                nuevos += 1
                if nuevos % 50 == 0:
                    guardar()
                    print(f"  [checkpoint] {len(hechos)} guardadas", flush=True)
            time.sleep(a.pausa)
        if not a.listar:
            guardar()

    print(f"\nTerminado: {nuevos} nuevas, {len(hechos)} en total, {len(fallos)} fallos")
    if fallos:
        (RAIZ / "_run" / "corte_texto_fallos.txt").write_text("\n".join(fallos), encoding="utf-8")
        print("Fallos en _run/corte_texto_fallos.txt (relanzar los reintenta)")


if __name__ == "__main__":
    main()
