#!/usr/bin/env python3
"""Cosecha cómo preguntan de verdad los colombianos, del autocompletar de Google.

Por qué hace falta. El banco de evaluación del proyecto lo redactó una IA
imitando cómo habla la gente, y el 12-sep-2026 quedó medido que el sistema
recupera bien para `abogado_junior` (61%) y **nada** para `adulto_mayor_informal`
y `baja_alfabetizacion` (0%). Ese diagnóstico se apoya en una imitación: nadie
ha comprobado que la gente pregunte como el banco supone. Aquí se traen frases
reales.

Sirve para tres cosas, por orden de importancia:

1. **Un banco de evaluación con validez real** en lugar de una imitación.
2. **Un puente de vocabulario dejado de adivinar**: se intentó minar de los 936
   pares sintéticos y salió ruido ("plata -> 2555"). Con frases reales se puede
   mirar qué palabras usa la gente y cuáles no aparecen nunca en la norma.
3. **Saber qué debe cubrir el corpus.** Hoy es fuerte en tributario y
   societario; puede no ser lo que más se consulta.

Lo que NO da: cuántas veces se buscó algo. El autocompletar ordena por
popularidad pero no publica volúmenes, y Google no publica sus registros de
búsqueda. Para volúmenes hace falta el Planificador de Palabras Clave de Google
Ads, que es el paso siguiente y pide cuenta.

Cortesía y límites: se consulta un endpoint público de sugerencias, uno cada
`ESPERA` segundos y con un tope de peticiones. No se recogen datos de personas:
las sugerencias son agregados, no consultas de nadie en concreto.

Uso:
    ./.venv/Scripts/python.exe finetune/recolectar_consultas_reales.py
    ./.venv/Scripts/python.exe finetune/recolectar_consultas_reales.py --max 400
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from confianza_tls import confiar_en_almacen_del_sistema  # noqa: E402

SALIDA = RAIZ / "finetune" / "eval" / "consultas_reales_google.json"
ESPERA = 0.45
TIEMPO_LIMITE = 15
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Arranques de frase con los que la gente formula un problema, no un concepto.
# Son la mitad del truco: pedir "arrendamiento" devuelve definiciones; pedir
# "me pueden sacar de la casa" devuelve cómo lo vive quien lo pregunta.
ARRANQUES = (
    "puedo",
    "me pueden",
    "que pasa si",
    "que hago si",
    "como hago para",
    "cuanto me",
    "cuando me",
    "tengo derecho a",
    "es legal que",
    "donde puedo",
    "me toca",
    "estoy obligado a",
)

# Semillas por materia, en lenguaje llano a propósito.
SEMILLAS = (
    # trabajo
    "me echaron del trabajo",
    "me deben la liquidacion",
    "vacaciones trabajo",
    "prima de servicios",
    "cesantias",
    "horas extras",
    "incapacidad medica trabajo",
    "licencia de maternidad",
    "licencia de paternidad",
    "acoso laboral",
    "contrato de prestacion de servicios",
    "renunciar al trabajo",
    # vivienda y servicios
    "contrato de arriendo",
    "el arrendador me quiere sacar",
    "aumento del arriendo",
    "administracion conjunto residencial",
    "me cortaron la luz",
    "cobro de servicios publicos",
    "impuesto predial",
    # consumo
    "garantia de un producto",
    "me estafaron por internet",
    "devolucion de dinero compra",
    "no me entregaron el producto",
    "reclamo a una empresa",
    # salud y pension
    "la eps no me autoriza",
    "tutela salud",
    "pension de vejez",
    "semanas cotizadas pension",
    "me negaron la pension",
    "cambiar de eps",
    # familia
    "cuota de alimentos",
    "custodia de los hijos",
    "divorcio en colombia",
    "herencia",
    "sucesion de bienes",
    "union libre derechos",
    "violencia intrafamiliar",
    # dinero y deudas
    "estoy reportado en datacredito",
    "me estan cobrando una deuda vieja",
    "prestamo gota a gota",
    "embargo de cuenta bancaria",
    "tarjeta de credito cobros",
    # trámites y Estado
    "derecho de peticion",
    "poner una tutela",
    "comparendo de transito",
    "licencia de conduccion",
    "sacar el rut",
    "declarar renta",
    "facturacion electronica",
    "camara de comercio matricula",
    # negocio
    "crear una empresa",
    "despedir a un empleado",
    "sociedad por acciones simplificada",
    "impuestos de un negocio",
)

# Ruido que el autocompletar trae y no es una consulta jurídica.
BASURA = re.compile(
    r"(?i)\b(meme|memes|cancion|letra|pelicula|serie|novela|frases?|chistes?|"
    r"como se escribe|en ingles|significado biblico|sue[nñ]o|suenos?|"
    r"youtube|tiktok|facebook|whatsapp|instagram)\b"
)


def sugerencias(texto: str) -> list[str]:
    """Consulta el autocompletar. Un fallo puntual no puede tumbar la cosecha."""
    url = (
        "https://suggestqueries.google.com/complete/search"
        "?client=firefox&hl=es&gl=co&q=" + urllib.parse.quote(texto)
    )
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_LIMITE) as r:
            datos = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"    (fallo en {texto!r}: {type(e).__name__})")
        return []
    return [s for s in datos[1] if isinstance(s, str)] if len(datos) > 1 else []


def util(frase: str, minimo: int = 4) -> bool:
    return len(frase.split()) >= minimo and not BASURA.search(frase)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=900, help="tope de peticiones")
    ap.add_argument("--sin-expandir", action="store_true", help="no profundiza un nivel")
    args = ap.parse_args()

    confiar_en_almacen_del_sistema()

    recogidas: dict[str, dict] = {}
    peticiones = 0

    def cosechar(texto: str, semilla: str, nivel: int) -> list[str]:
        nonlocal peticiones
        if peticiones >= args.max:
            return []
        peticiones += 1
        salida = sugerencias(texto)
        time.sleep(ESPERA)
        nuevas = []
        for s in salida:
            s = s.strip().lower()
            if s in recogidas or not util(s):
                continue
            recogidas[s] = {"consulta": s, "semilla": semilla, "nivel": nivel}
            nuevas.append(s)
        return nuevas

    print(f"{len(SEMILLAS)} semillas x {len(ARRANQUES) + 1} formas; tope {args.max} peticiones")
    for i, semilla in enumerate(SEMILLAS, 1):
        antes = len(recogidas)
        cosechar(semilla, semilla, 0)
        for arranque in ARRANQUES:
            if peticiones >= args.max:
                break
            cosechar(f"{arranque} {semilla}", semilla, 0)
        print(
            f"  [{i}/{len(SEMILLAS)}] {semilla[:38]:40} +{len(recogidas) - antes:3}  "
            f"(total {len(recogidas)}, {peticiones} peticiones)"
        )
        if peticiones >= args.max:
            print("  (tope de peticiones alcanzado)")
            break

    # Un nivel más: las frases cosechadas vuelven a preguntarse, que es donde
    # aparecen las variantes largas y concretas ("...si gano el minimo 2026").
    if not args.sin_expandir and peticiones < args.max:
        semillas2 = [c for c in list(recogidas.values()) if c["nivel"] == 0][:120]
        print(f"\nProfundizando sobre {len(semillas2)} frases...")
        for j, c in enumerate(semillas2, 1):
            if peticiones >= args.max:
                break
            cosechar(c["consulta"], c["semilla"], 1)
            if j % 20 == 0:
                print(f"  {j}/{len(semillas2)} (total {len(recogidas)})")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(
        json.dumps(sorted(recogidas.values(), key=lambda x: x["consulta"]), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\n{len(recogidas)} consultas reales en {SALIDA}")
    print(f"{peticiones} peticiones hechas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
