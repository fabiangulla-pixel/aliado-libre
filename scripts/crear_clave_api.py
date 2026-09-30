"""Emite una clave de pago para el servidor del índice.

Imprime la clave UNA vez (para entregársela al cliente) y la entrada que va en
`ALIADO_CLAVES_API`, que guarda solo su hash: si alguien lee la configuración
del servidor, no obtiene claves utilizables. Si el cliente pierde la clave, se
emite otra y se borra la entrada vieja.

Uso:
    .venv/Scripts/python.exe scripts/crear_clave_api.py "Bufete Pérez" 2000
    .venv/Scripts/python.exe scripts/crear_clave_api.py "Integración X" sin-tope
"""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servidor_indice.cuotas import hash_clave  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    nombre, tope_txt = sys.argv[1], sys.argv[2]
    tope = None if tope_txt == "sin-tope" else int(tope_txt)
    clave = "al_" + secrets.token_urlsafe(32)
    entrada = {hash_clave(clave): {"nombre": nombre, "tope_diario": tope}}
    print("Clave para el cliente (no se vuelve a mostrar):")
    print(f"  {clave}\n")
    print("Añadir a ALIADO_CLAVES_API (JSON; se fusiona con las existentes):")
    print(f"  {json.dumps(entrada, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
