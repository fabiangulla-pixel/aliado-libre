#!/usr/bin/env python3
"""Regenera las 20 consultas para auditoría con el filtro de ceremonial aplicado."""

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from index.buscar import IndiceBusqueda

# Las 20 consultas de la auditoría anterior
CONSULTAS_AUDIT = [
    "mi jefe dice que la otra empresa le robo los clientes como ago para que no pase eso",
    "que medallas le dan a los soldados del ejercito",
    "si uso el mismo nombre de otro negocio me pueden demandar",
    "desde cuando vale el decreto de febrero del 2000",
    "si me salgo de una empresa me devuelven la plata que puse",
    "cuanto se demoran en darme la plata de mi pension cuando pido el bono",
    "donde demando a la empresa de agua que me cobra de mas por el recibo",
    "cuanto ganan los profesores de los tecnologicos del gobierno",
    "cuanto pagan de mas a los jefes del senado",
    "cuantos diputados eligen en cada parte cuando votan",
    "como puedo saber cuantos empleados tiene la carcel inpec",
    "quien firmo la ley en el año 1943 en bogota",
    "cuanto tiempo dura una fiducia para casas de interes social",
    "porque me piden tantos papeles en la alcaldia si ya lleve unos",
    "cuando una eps esta vigilada le pagan todo o solo una parte",
    "como matan los animales en el matadero pa que no sufran",
    "cuando vendo algo y lo alquilo como ago con la plata que gane",
    "cuando alguien te copia el negocio como ago para denunciar si me estan copiando",
    "como ago para reclamar algo que mando la dian si no estoy de acuerdo",
    "como saver si el gobierno esta gastando bien la plata en los pobres",
]

indice = IndiceBusqueda()

print("Regenerando 20 consultas con filtro de ceremonial...")
print("(El filtro excluye fragmentos cortos que solo contienen 'Comuniquese', 'Dado en', etc.)\n")

casos = []
for i, consulta in enumerate(CONSULTAS_AUDIT, 1):
    print(f"{i:2d}. Buscando: {consulta[:60]}...", end=" ")
    resultados = indice.buscar(consulta, k=5)

    if not resultados:
        print("SIN RESULTADOS")
        continue

    # Los CINCO resultados, no solo el primero: la abogada juzga si la busqueda
    # responde la pregunta, y eso no se puede juzgar con un solo documento. La
    # hoja anterior mostraba top-1 y ademas no llegaba a imprimir los documentos.
    primer = resultados[0]
    caso = {
        "documentos": [
            {
                "orden": j,
                "fuente": r.get("fuente", ""),
                "identificador": r.get("identificador_documento", ""),
                "titulo": r.get("titulo_documento", ""),
                "texto": r.get("texto", ""),
                "longitud": len(r.get("texto", "")),
            }
            for j, r in enumerate(resultados[:5], 1)
        ],
        "consulta": consulta,
        "documento": primer.get("titulo_documento", ""),
        "fuente": primer.get("fuente", ""),
        "identificador": primer.get("identificador_documento", ""),
        "fragmento_preview": primer.get("texto", "")[:300] + "..."
        if len(primer.get("texto", "")) > 300
        else primer.get("texto", ""),
        "longitud_fragmento": len(primer.get("texto", "")),
        "puntaje": primer.get("puntaje", 0),
    }
    casos.append(caso)

    # Verificar si es basura
    # Frase completa, no subcadena: "FIRMA" esta dentro de "confirma" y "firmara",
    # que es el mismo fallo que mutilo el corpus entero el 9-sep-2026.
    texto_primero = primer.get("texto", "").strip().upper()
    es_basura = len(texto_primero) < 200 and bool(
        re.match(r"^[\s.,;:-]*(COMUNÍQUESE|COMUNIQUESE|DADO\s+EN|PUBLÍQUESE|PUBLIQUESE)", texto_primero)
    )

    estado = "OK" if not es_basura else "BASURA AUN PRESENTE"
    print(f"{estado} ({len(primer.get('texto', ''))} chars)")

# Guardar resultado
resultado = {
    "fecha": __import__("datetime").datetime.now().isoformat(),
    "total": len(casos),
    "casos": casos,
    "nota": "Regenerado con filtro de ceremonial en recuperación",
}

pathlib.Path("finetune/eval/20_casos_regenerados.json").write_text(
    json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
)

print("\nOK - 20 casos regenerados en: finetune/eval/20_casos_regenerados.json")
print("Verifica manualmente que NO hay 'Comuniquese y Cumplase' o ceremonial puro")
