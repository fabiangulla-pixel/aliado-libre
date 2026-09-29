"""Descarga el catálogo de vigencias de SUIN-Juriscol (datos.gov.co, dataset
fiev-nid6): ~89.000 normas con tipo, número, año y vigencia oficial.

Lo usa `index/build_vigencia.py` para marcar normas cuyo texto no trae nota de
vigencia (la mayoría de legalize_co_github). Sin texto completo: solo metadatos.

Uso:  .venv/Scripts/python.exe scripts/descargar_suin_vigencias.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from confianza_tls import confiar_en_almacen_del_sistema  # noqa: E402

URL = "https://www.datos.gov.co/resource/fiev-nid6.json?$limit=200000&$select=tipo,n_mero,a_o,vigencia"
DESTINO = Path(__file__).resolve().parent.parent / "data" / "suin_vigencias.json"


def main() -> None:
    confiar_en_almacen_del_sistema()
    with urllib.request.urlopen(URL, timeout=120) as r:
        datos = json.loads(r.read())
    if not isinstance(datos, list) or len(datos) < 50_000:
        raise SystemExit(f"Respuesta inesperada ({type(datos).__name__}, {len(datos)}): no se sobrescribe.")
    DESTINO.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    print(f"{len(datos)} registros -> {DESTINO}")


if __name__ == "__main__":
    main()
