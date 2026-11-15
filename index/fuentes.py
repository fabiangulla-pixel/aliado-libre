"""Catálogo de las entidades colombianas cubiertas por el índice.

Sirve para dos cosas a la vez, y esa doble función es deliberada:

1. **Filtrar.** El usuario puede acotar la consulta a una entidad o cruzar
   varias. Buscar "concepto sobre posición dominante" solo en la SIC devuelve
   algo muy distinto que buscarlo en 718.388 fragmentos de siete fuentes.
2. **Ser transparentes.** Mostrar la lista completa —con cuántos fragmentos
   trae cada una y qué **no** está— le dice al usuario dónde puede confiar y
   dónde no. Un vacío declarado es información útil; un vacío escondido hace
   que el usuario crea que buscó donde no buscó.

Los conteos se leen del índice léxico (FTS5), no de la colección vectorial: el
FTS es el mismo sin importar con qué modelo de embeddings esté construido el
vectorial, así que los números no cambian al reindexar.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

DB_FTS = Path(__file__).resolve().parent / "fts_index.db"


@dataclass
class Fuente:
    clave: str
    nombre: str
    entidad: str
    descripcion: str
    fragmentos: int = 0


# El orden es el de presentación: primero lo que un ciudadano reconoce.
CATALOGO: dict[str, Fuente] = {
    "corte_constitucional": Fuente(
        "corte_constitucional",
        "Corte Constitucional",
        "Corte Constitucional de Colombia",
        "Sentencias de constitucionalidad, tutela y unificación desde 1992. "
        "Es la fuente para derechos fundamentales, tutelas y salud.",
    ),
    "corte_suprema": Fuente(
        "corte_suprema",
        "Corte Suprema",
        "Corte Suprema de Justicia",
        "Sentencias de casación de las salas Laboral y Civil con texto digital "
        "(sobre todo desde 2017): contratos de trabajo, liquidaciones, pensiones, "
        "familia, contratos y responsabilidad civil.",
    ),
    "consejo_estado": Fuente(
        "consejo_estado",
        "Consejo de Estado",
        "Consejo de Estado",
        "Sentencias y autos de lo contencioso administrativo: demandas contra el "
        "Estado, servicios públicos, contratación estatal, empleo público y tutelas.",
    ),
    "gestor_normativo": Fuente(
        "gestor_normativo",
        "Gestor Normativo",
        "Departamento Administrativo de la Función Pública",
        "Leyes, decretos y resoluciones con su grafo de vigencias "
        "(qué norma modifica, deroga o reglamenta a cuál). Función pública, "
        "empleo estatal y contratación.",
    ),
    "legalize_co_github": Fuente(
        "legalize_co_github",
        "Compilación de decretos",
        "Respaldo abierto del histórico normativo",
        "El grueso del corpus: decretos nacionales completos. Sustituye a "
        "SUIN-Juriscol, cuyo portal bloquea el acceso automatizado.",
    ),
    "dian": Fuente(
        "dian",
        "DIAN",
        "Dirección de Impuestos y Aduanas Nacionales",
        "Doctrina y jurisprudencia tributaria, aduanera y cambiaria. Impuestos, retenciones, importaciones.",
    ),
    "supersociedades": Fuente(
        "supersociedades",
        "Supersociedades",
        "Superintendencia de Sociedades",
        "Conceptos jurídicos sobre sociedades: constitución, liquidación, "
        "cuotas, insolvencia, deberes de administradores.",
    ),
    "sic": Fuente(
        "sic",
        "SIC",
        "Superintendencia de Industria y Comercio",
        "Decisiones jurisdiccionales sobre protección al consumidor, "
        "competencia desleal, datos personales y propiedad industrial.",
    ),
    "superfinanciera": Fuente(
        "superfinanciera",
        "Superfinanciera",
        "Superintendencia Financiera de Colombia",
        "Conceptos y jurisprudencia sobre el sistema financiero: créditos, seguros, entidades vigiladas.",
    ),
    "superservicios": Fuente(
        "superservicios",
        "Superservicios",
        "Superintendencia de Servicios Públicos Domiciliarios",
        "Conceptos jurídicos sobre luz, agua, gas, aseo y telefonía fija: "
        "facturación, cortes, reconexión, reclamos y derechos del usuario.",
    ),
    "supersalud": Fuente(
        "supersalud",
        "Supersalud",
        "Superintendencia Nacional de Salud y Ministerio de Salud",
        "Conceptos seleccionados sobre EPS e IPS: afiliación, autorizaciones, "
        "traslados, cobros y prestación de servicios de salud.",
    ),
}

# Lo que NO está, y por qué. Se muestra junto al catálogo a propósito: el
# usuario tiene que poder saber cuándo el índice no puede ayudarle.
AUSENTES = (
    {
        "nombre": "Corte Suprema: sentencias antiguas y salas Penal y de Tutelas",
        "motivo": "Las sentencias anteriores a ~2017 están publicadas como PDF escaneado, "
        "sin texto: no se pueden buscar sin reconocimiento óptico de caracteres. "
        "Las salas Penal y de Tutelas no se han incorporado.",
    },
    {
        "nombre": "Conceptos del Ministerio del Trabajo",
        "motivo": "El Ministerio no publica un repositorio propio; las únicas copias "
        "encontradas están en compilaciones de una editorial privada con derechos reservados.",
    },
    {
        "nombre": "Diario Oficial (Imprenta Nacional)",
        "motivo": "Sin vía de acceso abierta resuelta todavía.",
    },
)

_conteos: dict[str, int] | None = None
_candado = threading.Lock()


def _contar() -> dict[str, int]:
    """Fragmentos por fuente, leídos del índice léxico.

    El id de cada fragmento empieza por su fuente ("sic:123::frag0"), así que
    contar por prefijo evita recorrer la metadata de la colección vectorial.
    """
    if not DB_FTS.exists():
        return {}
    conteos: dict[str, int] = {}
    con = sqlite3.connect(f"file:{DB_FTS}?mode=ro", uri=True)
    try:
        for (fid,) in con.execute("SELECT id FROM fragmentos_fts"):
            clave = fid.split(":", 1)[0]
            conteos[clave] = conteos.get(clave, 0) + 1
    finally:
        con.close()
    return conteos


def catalogo(refrescar: bool = False) -> list[Fuente]:
    """Las fuentes disponibles, con su número de fragmentos.

    Se cachea: recorrer 718.388 ids toma unos segundos y el resultado no cambia
    entre consultas.
    """
    global _conteos
    with _candado:
        if _conteos is None or refrescar:
            _conteos = _contar()
    salida = []
    for clave, fuente in CATALOGO.items():
        n = _conteos.get(clave, 0)
        if n == 0:
            continue  # no se anuncia una fuente que el índice no tiene
        salida.append(Fuente(fuente.clave, fuente.nombre, fuente.entidad, fuente.descripcion, n))
    return sorted(salida, key=lambda f: -f.fragmentos)


def normalizar(fuentes: list[str] | None) -> list[str] | None:
    """Deja solo claves de fuente conocidas; None si no hay filtro que aplicar.

    Un filtro con nombres inventados debe comportarse como "sin filtro" y no
    como "sin resultados": es más probable que sea un error de quien llama que
    una intención del usuario.
    """
    if not fuentes:
        return None
    validas = [f for f in fuentes if f in CATALOGO]
    return validas or None


def resumen() -> dict:
    """Estructura lista para el endpoint y la interfaz."""
    disponibles = catalogo()
    return {
        "total_fragmentos": sum(f.fragmentos for f in disponibles),
        "fuentes": [
            {
                "clave": f.clave,
                "nombre": f.nombre,
                "entidad": f.entidad,
                "descripcion": f.descripcion,
                "fragmentos": f.fragmentos,
            }
            for f in disponibles
        ],
        "ausentes": list(AUSENTES),
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    datos = resumen()
    print(f"{datos['total_fragmentos']:,} fragmentos".replace(",", "."))
    for f in datos["fuentes"]:
        print(f"  {f['nombre']:26} {f['fragmentos']:>7}  {f['entidad']}")
    print("\nNo disponibles:")
    for a in datos["ausentes"]:
        print(f"  {a['nombre']}: {a['motivo'][:80]}...")
