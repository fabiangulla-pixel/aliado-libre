"""Lanza un crawl real de Gestor Normativo a partir de varias normas semilla
importantes, guardando avances incrementalmente (checkpoint) para poder
reanudar si se interrumpe."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.fuentes.gestor_normativo import crawl
from ingest.schema import Documento

# Semillas: TODOS los decretos únicos reglamentarios sectoriales (uno por
# sector del Estado). Cada uno es raíz de un vecindario legal distinto en el
# grafo de vigencias -> cubrir todos evita que el BFS se quede solo en el
# vecindario de un par de sectores (lo que pasó con la primera corrida: 2073
# decretos pero apenas 1 resolución, sesgado hacia función pública/trabajo).
SEMILLAS = [
    "154466",  # Decreto 1821 de 2020 - Presidencia
    "73593",  # Decreto 1081 de 2015 - Interior
    "76835",  # Decreto 1066 de 2015 - Relaciones Exteriores
    "74000",  # Decreto 1067 de 2015 - Hacienda y Crédito Público
    "72893",  # Decreto 1068 de 2015 - Hacienda y Crédito Público
    "83233",  # Decreto 1625 de 2016 - Tributario
    "74174",  # Decreto 1069 de 2015 - Justicia y del Derecho
    "76837",  # Decreto 1070 de 2015 - Defensa
    "76838",  # Decreto 1071 de 2015 - Agropecuario, Pesquero y Desarrollo Rural
    "72173",  # Decreto 1072 de 2015 - Trabajo
    "85319",  # Decreto 1833 de 2016 - Sistema General de Pensiones
    "76608",  # Decreto 1074 de 2015 - Comercio, Industria y Turismo
    "76745",  # Decreto 2420 de 2015 - Normas de Contabilidad
    "77913",  # Decreto 1075 de 2015 - Educación
    "78153",  # Decreto 1076 de 2015 - Ambiente y Desarrollo Sostenible
    "77216",  # Decreto 1077 de 2015 - Vivienda, Ciudad y Territorio
    "77888",  # Decreto 1078 de 2015 - Tecnologías de la Información
    "77889",  # Decreto 1079 de 2015 - Transporte
    "76833",  # Decreto 1080 de 2015 - Cultura
    "77653",  # Decreto 1082 de 2015 - Planeación Nacional
    "62866",  # Decreto 1083 de 2015 - Función Pública
    "77715",  # Decreto 1084 de 2015 - Inclusión Social y Reconciliación
    "77714",  # Decreto 1085 de 2015 - Deporte
    "62870",  # Decreto 1170 de 2015 - Información Estadística
    "77813",  # Decreto 780 de 2016 - Salud y Protección Social
    # Códigos generales: el grafo de vigencias de los "decretos únicos"
    # anteriores resultó muy interconectado entre sí (una corrida ampliada
    # con 25 semillas de sector solo sumó 15 documentos nuevos) -- los
    # códigos son universos de modificación separados, abren territorio
    # genuinamente nuevo en vez de reconverger al mismo núcleo.
    "41102",  # Decreto 410 de 1971 - Código de Comercio
    "199983",  # Decreto 2663 de 1950 - Código Sustantivo del Trabajo
    "6388",  # Ley 599 de 2000 - Código Penal
    "39535",  # Ley 57 de 1887 - adopta el Código Civil
    "48425",  # Ley 1564 de 2012 - Código General del Proceso
    "41249",  # Ley 1437 de 2011 - CPACA (procedimiento administrativo)
    # Leyes generales importantes, fuera del grafo de los decretos únicos:
    "304",  # Ley 80 de 1993 - Estatuto de Contratación Estatal
    "80538",  # Ley 1801 de 2016 - Código Nacional de Policía y Convivencia
    "22106",  # Ley 1098 de 2006 - Código de la Infancia y la Adolescencia
    "14787",  # Ley 906 de 2004 - Código de Procedimiento Penal
    "6533",  # Decreto 624 de 1989 - Estatuto Tributario
    "49981",  # Ley 1581 de 2012 - Habeas Data / Protección de Datos Personales
    "292",  # Ley 115 de 1994 - Ley General de Educación
    "22657",  # Ley 1116 de 2006 - Régimen de Insolvencia Empresarial
    "4162",  # Ley 675 de 2001 - Régimen de Propiedad Horizontal
]

SALIDA = Path(__file__).resolve().parent.parent / "data" / "raw" / "gestor_normativo.json"
CHECKPOINT_CADA = 25


def main() -> None:
    max_documentos = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    pausa = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5

    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    documentos_previos: list[Documento] = []
    if SALIDA.exists():
        datos = json.loads(SALIDA.read_text(encoding="utf-8"))
        documentos_previos = [Documento(**d) for d in datos]
        print(f"{len(documentos_previos)} documentos previos cargados, no se vuelven a descargar")

    print(f"Crawl objetivo: {max_documentos} documentos totales, pausa {pausa}s entre requests nuevos")

    def checkpoint(documentos):
        SALIDA.write_text(
            json.dumps([d.to_dict() for d in documentos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[checkpoint] {len(documentos)} documentos guardados en {SALIDA}", flush=True)

    documentos = crawl(
        SEMILLAS,
        max_documentos=max_documentos,
        pausa_segundos=pausa,
        al_guardar=checkpoint,
        documentos_previos=documentos_previos,
    )
    checkpoint(documentos)
    print(f"Terminado: {len(documentos)} documentos en {SALIDA}")


if __name__ == "__main__":
    main()
