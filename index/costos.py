"""Estimación y liquidación del costo de usar una IA externa.

Regla del proyecto: **antes** de gastar, se muestra el estimado; **después**, lo
que costó de verdad. El usuario paga con su propia clave, así que tiene derecho
a saber cuánto va a gastar antes de apretar el botón, no a enterarse en la
factura.

Los precios son públicos, en dólares por millón de tokens, y **caducan**: hay
que revisarlos cuando los proveedores los cambien. `VERIFICADO` dice cuándo se
comprobaron por última vez. Un precio desactualizado es peor que ninguno,
porque el usuario confía en él — por eso `estimar` avisa cuando el precio está
viejo en vez de callarse.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

VERIFICADO = _dt.date(2026, 9, 6)
MESES_HASTA_CADUCAR = 3

# USD por millón de tokens: (entrada, salida).
PRECIOS = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    # Corre en la máquina del usuario: no cuesta dinero, cuesta tiempo.
    "llama3.1": (0.0, 0.0),
}

# Un carácter de español pesa aproximadamente esto en tokens. Sirve para
# estimar ANTES de llamar; el número real sale del `usage` que devuelve el
# proveedor.
TOKENS_POR_CARACTER = 0.28
TOKENS_SALIDA_ESTIMADOS = 400
TRM_APROXIMADA = 4100  # pesos colombianos por dólar, solo para orientar


@dataclass
class Costo:
    usd: float
    tokens_entrada: int
    tokens_salida: int
    modelo: str
    estimado: bool
    aviso: str = ""

    @property
    def pesos(self) -> int:
        return round(self.usd * TRM_APROXIMADA)

    def texto(self) -> str:
        """Frase lista para mostrarle al usuario."""
        if self.usd == 0:
            return "Sin costo: corre en tu equipo."
        cabeza = "Costo estimado" if self.estimado else "Costo real"
        if self.usd < 0.01:
            monto = f"menos de un centavo de dólar (~${self.pesos} COP)"
        else:
            monto = f"US${self.usd:.4f} (~${self.pesos} COP)"
        # separador de miles con punto, como se escribe en Colombia
        entrada = f"{self.tokens_entrada:,}".replace(",", ".")
        salida = f"{self.tokens_salida:,}".replace(",", ".")
        return f"{cabeza}: {monto} — {entrada} tokens de entrada y {salida} de salida."


def _precio_caducado() -> str:
    meses = (_dt.date.today() - VERIFICADO).days / 30.44
    if meses > MESES_HASTA_CADUCAR:
        return (
            f"Los precios se verificaron por última vez el {VERIFICADO.isoformat()}, "
            f"hace más de {MESES_HASTA_CADUCAR} meses: el estimado puede estar desfasado."
        )
    return ""


def estimar(prompt: str, modelo: str, tokens_salida: int = TOKENS_SALIDA_ESTIMADOS) -> Costo:
    """Cuánto costaría, aproximadamente, mandar `prompt` a `modelo`."""
    if modelo not in PRECIOS:
        return Costo(
            0.0,
            0,
            0,
            modelo,
            True,
            f"No conocemos el precio de {modelo}: consúltalo con tu proveedor antes de usarlo.",
        )
    entrada, salida = PRECIOS[modelo]
    n_entrada = int(len(prompt) * TOKENS_POR_CARACTER)
    usd = n_entrada / 1e6 * entrada + tokens_salida / 1e6 * salida
    return Costo(usd, n_entrada, tokens_salida, modelo, True, _precio_caducado())


def liquidar(usage: object, modelo: str) -> Costo:
    """Cuánto costó de verdad, a partir del `usage` que devolvió el proveedor."""
    if modelo not in PRECIOS or usage is None:
        return Costo(0.0, 0, 0, modelo, False, "El proveedor no informó el consumo.")

    # Cada SDK nombra distinto lo mismo.
    n_entrada = (
        getattr(usage, "input_tokens", None)
        or getattr(usage, "prompt_tokens", None)
        or getattr(usage, "prompt_token_count", None)
        or 0
    )
    n_salida = (
        getattr(usage, "output_tokens", None)
        or getattr(usage, "completion_tokens", None)
        or getattr(usage, "candidates_token_count", None)
        or 0
    )
    entrada, salida = PRECIOS[modelo]
    usd = n_entrada / 1e6 * entrada + n_salida / 1e6 * salida
    return Costo(usd, int(n_entrada), int(n_salida), modelo, False, _precio_caducado())
