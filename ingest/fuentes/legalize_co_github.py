"""Ingester del respaldo local de `legalize-dev/legalize-co` (GitHub), clonado
en `data/respaldo_legalize_co/`. Es la fuente pensada como respaldo de
SUIN-Juriscol (bloqueado por WAF) — cada archivo es un Markdown con YAML
front matter (`title`, `identifier`, `rank`, `publication_date`, `status`,
`source`, ...) y el texto completo de la norma debajo.

No hace ninguna petición de red: lee del clon local. También resuelve, de
paso, el techo de ~2.381 normas del BFS de Gestor Normativo — este repo trae
**61.429 decretos** completos sin depender del grafo de "Vigencias"."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ingest.schema import Documento

RAIZ_DEFECTO = Path(__file__).parent.parent.parent / "data" / "respaldo_legalize_co" / "co"

TIPO_POR_RANK = {
    "ley": "ley",
    "decreto": "decreto",
    "decreto ley": "decreto",
    "decreto-ley": "decreto",
    "resolucion": "resolucion",
    "resolución": "resolucion",
}


def _parsear_archivo(ruta: Path) -> Documento | None:
    crudo = ruta.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", crudo, re.DOTALL)
    if not m:
        return None

    try:
        front_matter = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None

    texto = m.group(2).strip()
    if len(texto) < 40:
        return None

    identificador = front_matter.get("identifier") or ruta.stem
    rank = (front_matter.get("rank") or "").lower()
    tipo = TIPO_POR_RANK.get(rank, "ley")

    return Documento(
        id=f"legalize_co_github:{identificador}",
        fuente="legalize_co_github",
        tipo=tipo,
        identificador=identificador,
        titulo=front_matter.get("title") or identificador,
        fecha=front_matter.get("publication_date"),
        texto=texto,
        url_original=front_matter.get("source") or "https://github.com/legalize-dev/legalize-co",
        metadata={
            "rank_original": front_matter.get("rank"),
            "status": front_matter.get("status"),
            "department": front_matter.get("department"),
            "gazette_reference": front_matter.get("gazette_reference"),
        },
    )


def crawl(max_documentos: int = 5000, raiz: Path | None = None, al_guardar=None) -> list[Documento]:
    raiz = raiz or RAIZ_DEFECTO
    if not raiz.is_dir():
        raise FileNotFoundError(
            f"No se encontró el clon local de legalize-co en {raiz}. "
            "Clonar con: git clone --depth 1 https://github.com/legalize-dev/legalize-co.git "
            "data/respaldo_legalize_co"
        )

    documentos: list[Documento] = []
    for i, ruta in enumerate(sorted(raiz.glob("*.md"))):
        if len(documentos) >= max_documentos:
            break
        doc = _parsear_archivo(ruta)
        if doc is not None:
            documentos.append(doc)
        if al_guardar is not None and i % 1000 == 0:
            al_guardar(documentos)

    return documentos
