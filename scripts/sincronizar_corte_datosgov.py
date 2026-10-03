#!/usr/bin/env python3
"""Compara las sentencias de la Corte Constitucional del corpus con el registro oficial.

El registro abierto de la Corte en datos.gov.co (conjunto v2k4-2t8s, sin clave)
lista todas las sentencias desde 1992 con su número canónico ("T-760/08"),
fecha, magistrado y sala. Contrastarlo con el catálogo de citas dice:

- qué sentencias FALTAN en el corpus (para ingerirlas), por año y por tipo;
- cuáles tenemos que el registro no conoce (posible error de título).

No modifica el índice: escribe el informe en `_run/sincronizacion_corte.json`.
Requiere el catálogo (`index/resolver_citas.py --construir`).

Uso:
    .venv/Scripts/python.exe scripts/sincronizar_corte_datosgov.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from index.citas import parsear_cita  # noqa: E402
from index.resolver_citas import CATALOGO  # noqa: E402

URL = "https://www.datos.gov.co/resource/v2k4-2t8s.json"
PAGINA = 50000
SALIDA = RAIZ / "_run" / "sincronizacion_corte.json"


def descargar() -> list[dict]:
    filas: list[dict] = []
    while True:
        url = f"{URL}?$limit={PAGINA}&$offset={len(filas)}&$order=sentencia"
        with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 - URL fija del Estado
            lote = json.loads(r.read().decode("utf-8"))
        filas.extend(lote)
        if len(lote) < PAGINA:
            return filas


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not CATALOGO.exists():
        print("Falta el catálogo: corre index/resolver_citas.py --construir")
        return 1
    cat = json.loads(CATALOGO.read_text(encoding="utf-8"))
    nuestras = {k.split("|", 1)[1] for k in cat["exacto"] if k.startswith("sentencia|")}

    filas = descargar()
    oficiales: dict[str, dict] = {}
    for f in filas:
        c = parsear_cita(f.get("sentencia", ""))
        if c and c.sentencia:
            oficiales[c.sentencia] = f

    faltan = sorted(set(oficiales) - nuestras)
    sobran = sorted(s for s in nuestras - set(oficiales) if not s.startswith("A-"))
    por_anio = Counter(oficiales[s]["fecha_sentencia"][:4] for s in faltan)
    por_tipo = Counter(s.split("-")[0] for s in faltan)

    print(f"Registro oficial: {len(filas)} filas, {len(oficiales)} sentencias reconocidas")
    print(f"En el corpus: {len(nuestras)} sentencias/autos de la Corte")
    print(f"Faltan en el corpus: {len(faltan)} ({len(faltan) / max(len(oficiales), 1) * 100:.1f}%)")
    print("  por tipo:", dict(por_tipo.most_common()))
    print("  por año (los 10 con más):", dict(por_anio.most_common(10)))
    print(f"En el corpus pero no en el registro (sin contar autos): {len(sobran)}")

    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(
        json.dumps(
            {
                "fuente": URL,
                "filas_oficiales": len(filas),
                "faltan": [{"sentencia": s, **oficiales[s]} for s in faltan],
                "sobran_muestra": sobran[:200],
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"Detalle en {SALIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
