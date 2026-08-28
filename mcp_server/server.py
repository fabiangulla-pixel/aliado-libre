"""Servidor MCP de Aliado Libre: expone el índice legal colombiano como
herramientas para Claude u otro cliente MCP. Equivalente libre y gratuito
al conector de aliado.pro."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from index.buscar import IndiceBusqueda

mcp = FastMCP("aliado-libre")
_indice: IndiceBusqueda | None = None


def _obtener_indice() -> IndiceBusqueda:
    global _indice
    if _indice is None:
        _indice = IndiceBusqueda()
    return _indice


@mcp.tool()
def buscar_normativa(consulta: str, max_resultados: int = 5) -> str:
    """Busca legislación y jurisprudencia colombiana relevante a una consulta.
    Devuelve fragmentos con su fuente, identificador y URL original para citar.
    IMPORTANTE: si no hay resultados relevantes, dilo explícitamente — no inventes."""
    resultados = _obtener_indice().buscar(consulta, k=max_resultados)
    if not resultados:
        return "Sin resultados en el índice actual para esta consulta."

    partes = []
    for r in resultados:
        partes.append(
            f"### {r['titulo_documento']}\n"
            f"Fuente: {r['fuente']} | Identificador: {r['identificador_documento']}\n"
            f"URL: {r['url_original']}\n"
            f"Fragmento:\n{r['texto']}\n"
        )
    return "\n---\n".join(partes)


if __name__ == "__main__":
    mcp.run()
