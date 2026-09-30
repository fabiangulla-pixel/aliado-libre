"""Emite claves de pago para el servidor del índice.

Planes (modelo freemium del 29-sep-2026; precios en docs/PLANES.md):

    pase-dia     sigue consultando hoy, pasado el tope gratuito
    mensual      membresía mensual con tope de consultas por mes
    pro          por usuario, sin tope, un mes
    empresarial  como pro, emitida para N usuarios (--usuarios)
    gold         pago único: sin tope durante π años (1.147 días) desde hoy

Imprime cada clave UNA vez (para entregársela al cliente) y la entrada para
`ALIADO_CLAVES_API`, que guarda solo su hash: quien lea la configuración del
servidor no obtiene claves utilizables. Si un cliente pierde su clave, se emite
otra y se borra la entrada vieja.

Uso:
    .venv/Scripts/python.exe scripts/crear_clave_api.py gold "Ana Pérez"
    .venv/Scripts/python.exe scripts/crear_clave_api.py mensual "Juan" --tope 100
    .venv/Scripts/python.exe scripts/crear_clave_api.py empresarial "Bufete X" --usuarios 12
"""

from __future__ import annotations

import argparse
import json
import math
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servidor_indice.cuotas import hash_clave, hoy  # noqa: E402

# π años en días, redondeado hacia abajo: 3,14159… × 365,2425 = 1.147,49.
DIAS_GOLD = math.floor(math.pi * 365.2425)
DIAS_MES = 31

# plan -> (tope, periodo, días de validez desde hoy; 0 = solo hoy)
PLANES = {
    "pase-dia": (100, "dia", 0),
    "mensual": (100, "mes", DIAS_MES),
    "pro": (None, "mes", DIAS_MES),
    "empresarial": (None, "mes", DIAS_MES),
    "gold": (None, "dia", DIAS_GOLD),
}


def emitir(plan: str, nombre: str, tope: int | None = None, desde: date | None = None) -> tuple[str, dict]:
    tope_plan, periodo, dias = PLANES[plan]
    inicio = desde or date.fromisoformat(hoy())
    clave = "al_" + secrets.token_urlsafe(32)
    entrada = {
        "nombre": nombre,
        "plan": plan,
        "tope": tope if tope is not None else tope_plan,
        "periodo": periodo,
        "vence": (inicio + timedelta(days=dias)).isoformat(),
        "emitida": inicio.isoformat(),
    }
    return clave, {hash_clave(clave): entrada}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", choices=sorted(PLANES))
    ap.add_argument("nombre")
    ap.add_argument("--tope", type=int, default=None, help="cambia el tope del plan")
    ap.add_argument("--usuarios", type=int, default=1, help="cuántas claves emitir (una por persona)")
    a = ap.parse_args()

    entradas: dict = {}
    print(f"Plan {a.plan} para {a.nombre}. Claves (no se vuelven a mostrar):")
    for i in range(a.usuarios):
        nombre = a.nombre if a.usuarios == 1 else f"{a.nombre} #{i + 1}"
        clave, entrada = emitir(a.plan, nombre, a.tope)
        entradas.update(entrada)
        print(f"  {nombre}: {clave}")
    vence = next(iter(entradas.values()))["vence"]
    print(f"\nVence: {vence} (inclusive)")
    print("\nAñadir a ALIADO_CLAVES_API (JSON; se fusiona con las existentes):")
    print(f"  {json.dumps(entradas, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
