"""Esquema común al que convergen todas las fuentes antes de indexar."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date
from typing import Literal

TipoDocumento = Literal[
    "ley", "decreto", "resolucion", "sentencia", "concepto", "circular"
]

Fuente = Literal[
    "gestor_normativo", "diario_oficial", "corte_constitucional",
    "consejo_estado", "corte_suprema", "supersociedades", "dian",
    "superfinanciera", "sic", "leyes_colombianas_github", "legalize_co_github",
]


@dataclass
class Documento:
    id: str
    fuente: Fuente
    tipo: TipoDocumento
    identificador: str
    titulo: str
    fecha: str | None
    texto: str
    url_original: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
