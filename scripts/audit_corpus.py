"""Auditoría de integridad del corpus crudo (data/raw/*.json) antes de indexar."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVOS = ["gestor_normativo.json", "supersociedades.json", "corte_constitucional.json", "sic.json"]
CAMPOS_REQUERIDOS = {
    "id",
    "fuente",
    "tipo",
    "identificador",
    "titulo",
    "fecha",
    "texto",
    "url_original",
    "metadata",
}
PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}")
PATRON_MOJIBAKE = re.compile(r"Ã[\x80-\xbf¡-¿]|â€|Â[^\s\d]")


def cargar_todo() -> dict[str, list[dict]]:
    datos = {}
    for archivo in ARCHIVOS:
        ruta = RAIZ / "data" / "raw" / archivo
        if ruta.exists():
            datos[archivo] = json.loads(ruta.read_text(encoding="utf-8"))
        else:
            datos[archivo] = []
    return datos


def auditar():
    datos = cargar_todo()
    lineas = ["# Auditoría del corpus crudo\n"]
    todos_los_ids: Counter = Counter()
    ids_por_fuente: dict[str, set[str]] = {}

    total_docs = sum(len(v) for v in datos.values())
    lineas.append(f"**Total de documentos**: {total_docs}\n")

    for archivo, docs in datos.items():
        lineas.append(f"\n## {archivo} ({len(docs)} documentos)\n")
        if not docs:
            lineas.append("- Vacío o no encontrado.\n")
            continue

        # 1. Esquema
        campos_faltantes = Counter()
        for d in docs:
            faltan = CAMPOS_REQUERIDOS - set(d.keys())
            for f in faltan:
                campos_faltantes[f] += 1
        if campos_faltantes:
            lineas.append(f"- ⚠️ Campos faltantes: {dict(campos_faltantes)}\n")
        else:
            lineas.append("- ✅ Todos los documentos tienen los 9 campos del esquema.\n")

        # 2. IDs duplicados (dentro del archivo)
        ids = [d.get("id") for d in docs]
        contador_ids = Counter(ids)
        duplicados = {k: v for k, v in contador_ids.items() if v > 1}
        if duplicados:
            ejemplo = list(duplicados.items())[:3]
            lineas.append(f"- 🔴 {len(duplicados)} IDs duplicados dentro del archivo (ej: {ejemplo})\n")
        else:
            lineas.append("- ✅ Sin IDs duplicados dentro del archivo.\n")
        todos_los_ids.update(ids)
        ids_por_fuente[archivo] = set(ids)

        # 3. Texto vacío / sospechosamente corto
        textos_vacios = sum(1 for d in docs if not d.get("texto", "").strip())
        textos_cortos = sum(1 for d in docs if 0 < len(d.get("texto", "")) < 50)
        lineas.append(f"- Texto vacío: {textos_vacios} | Texto < 50 caracteres: {textos_cortos}\n")

        # 4. Longitud de texto (distribución)
        longitudes = sorted(len(d.get("texto", "")) for d in docs)
        if longitudes:
            mediana = longitudes[len(longitudes) // 2]
            lineas.append(
                f"- Longitud de texto: min={longitudes[0]}, mediana={mediana}, "
                f"max={longitudes[-1]}, promedio={sum(longitudes) // len(longitudes)}\n"
            )

        # 5. Fecha: nulos y formato
        fechas_nulas = sum(1 for d in docs if not d.get("fecha"))
        fechas_mal_formadas = sum(
            1 for d in docs if d.get("fecha") and not PATRON_FECHA.match(str(d["fecha"]))
        )
        pct_nulas = fechas_nulas * 100 // len(docs)
        lineas.append(f"- Fecha nula: {fechas_nulas} ({pct_nulas}%)\n")
        lineas.append(f"- Fecha con formato inválido: {fechas_mal_formadas}\n")

        # 6. url_original vacía
        urls_vacias = sum(1 for d in docs if not d.get("url_original", "").strip())
        lineas.append(f"- URL original vacía: {urls_vacias}\n")

        # 7. Mojibake residual (heurística: patrones típicos de doble-codificación)
        con_mojibake = sum(1 for d in docs if PATRON_MOJIBAKE.search(d.get("texto", "")[:5000]))
        pct_mojibake = con_mojibake * 100 // len(docs)
        linea_mojibake = f"- Posible mojibake residual (heurística): {con_mojibake} ({pct_mojibake}%)\n"
        lineas.append(linea_mojibake)

        # 8. tipo: valores únicos
        tipos = Counter(d.get("tipo") for d in docs)
        lineas.append(f"- Valores de `tipo`: {dict(tipos)}\n")

        # 9. Identificador vacío
        ident_vacios = sum(1 for d in docs if not d.get("identificador", "").strip())
        lineas.append(f"- `identificador` vacío: {ident_vacios}\n")

    # 10. IDs duplicados ENTRE archivos (no deberían chocar por el prefijo de fuente, pero se verifica)
    lineas.append("\n## Integridad cruzada\n")
    duplicados_globales = {k: v for k, v in todos_los_ids.items() if v > 1}
    if duplicados_globales:
        ejemplo = list(duplicados_globales.items())[:5]
        lineas.append(f"- 🔴 {len(duplicados_globales)} IDs duplicados ENTRE archivos: {ejemplo}\n")
    else:
        total_ids = sum(len(s) for s in ids_por_fuente.values())
        n_fuentes = len(ARCHIVOS)
        lineas.append(f"- Sin colisión de IDs entre las {n_fuentes} fuentes ({total_ids} IDs únicos).\n")

    # 11. Referencias rotas en vigencias (Gestor Normativo)
    gn = datos.get("gestor_normativo.json", [])
    if gn:
        ids_gn = {d["id"].split(":", 1)[1] for d in gn}
        total_vigencias = 0
        vigencias_rotas = 0
        for d in gn:
            for v in d.get("metadata", {}).get("vigencias", []):
                total_vigencias += 1
                if v["id_relacionado"] not in ids_gn:
                    vigencias_rotas += 1
        pct = (vigencias_rotas * 100 // total_vigencias) if total_vigencias else 0
        lineas.append(
            f"\n## Grafo de vigencias (Gestor Normativo)\n"
            f"- {total_vigencias} relaciones totales, {vigencias_rotas} apuntan a normas fuera del corpus "
            f"({pct}% -- ESPERADO: no se descargó todo el grafo completo, no es un bug).\n"
        )

    salida = RAIZ / "DATA_AUDIT.md"
    salida.write_text("".join(lineas), encoding="utf-8")
    print(f"Auditoría guardada en {salida}")
    print("".join(lineas))


if __name__ == "__main__":
    auditar()
