"""Traduce una consulta en lenguaje corriente al vocabulario de las normas.

El problema que resuelve, medido: la búsqueda es híbrida (FTS5 léxico +
embeddings). El componente léxico pesa el doble porque el embedding
multilingüe genérico casi no aporta hallazgos únicos sobre español jurídico
(ver index/buscar.py). Eso la hace muy sensible al vocabulario: si el usuario
escribe "quien recoge las ramas que corté", ninguno de esos términos aparece en
la norma, que habla de "recolección y transporte de residuos originados por el
arreglo de jardines". La consulta original va a competir contra el corpus con
palabras que el corpus no usa.

La reescritura no responde nada ni decide nada: solo produce los términos con
los que buscar. La pregunta original se conserva para redactar la respuesta.

Se reusa el modelo ya cargado por index/responder.py — es el mismo GGUF en
memoria, así que no cuesta RAM adicional.
"""

from __future__ import annotations

import re

# Corto a propósito: la salida son términos de búsqueda, no prosa. Un límite
# alto invita al modelo a explicar, y las explicaciones ensucian la consulta.
MAX_TOKENS = 60
TEMPERATURA = 0.1
STOPS = ["\n\n", "Consulta:", "###"]

PROMPT = """Eres un buscador de legislación colombiana. Traduce la consulta de un
ciudadano a los términos que usaría la norma escrita.

Devuelve SOLO los términos de búsqueda, en una línea, sin explicar y sin inventar números de norma.

Consulta: quien recoge las ramas que corté del arbol del antejardin
Términos: recolección transporte residuos poda de árboles corte de césped áreas públicas servicio de aseo

Consulta: me pueden echar del trabajo por estar embarazada
Términos: estabilidad laboral reforzada fuero de maternidad despido mujer embarazada

Consulta: {consulta}
Términos:"""


# Un modelo de 1.5B se atasca en bucle: "contratación de trabajadores de aduanas
# contratación de trabajadores de aduanas...". Medido en pruebas reales. Como la
# consulta reescrita SUSTITUYE a la del usuario, dejar pasar eso es peor que no
# reescribir: la búsqueda quedaría dominada por una palabra repetida.
MAX_PALABRAS = 16
REPETICION_MAXIMA = 0.55  # proporción de palabras distintas por debajo de la cual se descarta


def _limpiar(texto: str) -> str:
    texto = texto.strip().split("\n")[0]
    # el modelo a veces devuelve 'Términos: x' o comillas; sobran
    texto = re.sub(r"^\s*(términos|terminos)\s*:\s*", "", texto, flags=re.IGNORECASE)
    return texto.strip().strip('"').strip()


def _degenerada(texto: str) -> bool:
    palabras = [p for p in re.findall(r"\w+", texto.lower()) if len(p) > 2]
    if len(palabras) < 4:
        return False
    return len(set(palabras)) / len(palabras) < REPETICION_MAXIMA


def _compactar(texto: str) -> str:
    """Quita palabras repetidas conservando el orden y recorta a MAX_PALABRAS.

    Repetir un término en FTS5 no lo pondera más, solo alarga la consulta.
    """
    vistas: set[str] = set()
    salida: list[str] = []
    for palabra in texto.split():
        clave = re.sub(r"\W", "", palabra.lower())
        if clave and clave in vistas:
            continue
        if clave:
            vistas.add(clave)
        salida.append(palabra)
        if len(salida) >= MAX_PALABRAS:
            break
    return " ".join(salida)


def reescribir(consulta: str, minimo_palabras: int = 3) -> str:
    """Devuelve términos de búsqueda para `consulta`.

    Ante cualquier duda devuelve la consulta original: una reescritura mala es
    peor que ninguna, porque sustituye por completo lo que el usuario escribió.
    """
    if not consulta or not consulta.strip():
        return consulta

    from index.responder import cargar_modelo

    modelo = cargar_modelo()
    salida = modelo(
        PROMPT.format(consulta=consulta.strip()),
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURA,
        stop=STOPS,
    )
    reescrita = _limpiar(salida["choices"][0]["text"])

    if _degenerada(reescrita):
        return consulta
    reescrita = _compactar(reescrita)
    if len(reescrita.split()) < minimo_palabras:
        return consulta
    return reescrita


def reescribir_o_original(consulta: str) -> str:
    """Igual que `reescribir`, pero nunca propaga un fallo del modelo.

    Pensado para producción: si falta el GGUF o la inferencia revienta, la
    búsqueda debe seguir funcionando con la consulta cruda.
    """
    try:
        return reescribir(consulta)
    except Exception:  # noqa: BLE001
        return consulta


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    consulta = " ".join(sys.argv[1:]) or "¿Puedo tener el monopolio de las comunicaciones? Soy Tigo"
    print(f"original:  {consulta}")
    print(f"reescrita: {reescribir(consulta)}")
