"""Comprueba que lo comprobable de una respuesta esté en los fragmentos.

Determinista y sin IA: no juzga si la respuesta es buena, solo si cada dato
verificable que afirma (número de norma, artículo, fecha, cifra, plazo) aparece
de verdad en el texto que el modelo tenía delante. Un dato que no aparece es,
por definición, inventado — el modelo no tenía de dónde sacarlo.

Por qué hace falta, con un caso real medido: preguntado por la recolección de
residuos de poda, el modelo respondió citando "Decreto 605 de 1996" cuando el
fragmento decía "Decreto 1713 de 2002". La prosa era impecable y la cita,
falsa. Ningún prompt evita eso de forma fiable; una comprobación de cadenas, sí.

Lo que NO hace: decidir si la respuesta contesta la pregunta, ni si el
razonamiento es correcto. Solo ancla los datos duros.

Uso como biblioteca:
    from index.verificar_anclaje import verificar
    informe = verificar(respuesta, fragmentos)
    if not informe.anclada:
        ...  # marcar, tachar o suprimir
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Tipos de norma que se citan en el corpus colombiano.
_TIPOS_NORMA = (
    r"ley(?:es)?|decreto(?:s)?|resoluci[oó]n(?:es)?|circular(?:es)?|acuerdo(?:s)?|"
    r"ordenanza(?:s)?|sentencia(?:s)?|auto(?:s)?|concepto(?:s)?|oficio(?:s)?"
)

PATRONES = {
    # "Ley 909 de 2004", "Decreto 1713 de 2002", "Resolución DIAN 0035 de 2020"
    "norma": re.compile(
        rf"\b(?:{_TIPOS_NORMA})\b(?:\s+[A-ZÁÉÍÓÚÑ]{{2,}})?\s*(?:n[uú]mero\s*|n[°º.]\s*)?"
        r"(\d{1,5})\s*(?:de|del)\s*(\d{4})",
        re.IGNORECASE,
    ),
    # "artículo 24", "art. 2.2.5.3.1", "artículos 40 y 41"
    "articulo": re.compile(
        r"\bart[íi]culos?\b\.?\s*(\d+(?:\.\d+)*)|" r"\bart\.\s*(\d+(?:\.\d+)*)", re.IGNORECASE
    ),
    # sentencias: C-535/97, T-760 de 2008, SU-047/99
    "sentencia": re.compile(r"\b([CTSU]{1,2}-\d{1,4})\s*[/ ]\s*(?:de\s*)?(\d{2,4})", re.IGNORECASE),
    # plazos y cantidades con unidad: "seis (6) meses", "30 días", "2 años"
    "cantidad": re.compile(
        r"\b(\d{1,6})\s*(d[íi]as?|meses?|a[nñ]os?|horas?|smmlv|uvt|salarios?)\b", re.IGNORECASE
    ),
    "porcentaje": re.compile(r"\b(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:%|por ciento)"),
}

# Palabras que el modelo usa para hablar de sí mismo o del índice: nunca son
# afirmaciones sobre el derecho y no deben verificarse.
_FRASES_META = (
    "no encontré",
    "no encontre",
    "no hay información",
    "no hay informacion",
    "el índice",
    "el indice",
    "no puedo determinar",
)


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados.

    El corpus mezcla "ARTÍCULO", "Artículo" y "artículo", y el modelo escribe
    con tildes donde la norma a veces no las tiene. Comparar en crudo produciría
    falsos positivos por pura tipografía.
    """
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


@dataclass
class Afirmacion:
    tipo: str
    texto: str
    clave: str  # forma normalizada que se busca en los fragmentos
    respaldada: bool = False


@dataclass
class Informe:
    afirmaciones: list[Afirmacion] = field(default_factory=list)
    frases_sin_respaldo: list[str] = field(default_factory=list)

    @property
    def anclada(self) -> bool:
        """True si todo dato comprobable está en los fragmentos.

        Una respuesta sin datos comprobables (p. ej. una abstención) cuenta
        como anclada: no afirma nada que pueda ser falso.
        """
        return all(a.respaldada for a in self.afirmaciones)

    @property
    def sin_respaldo(self) -> list[Afirmacion]:
        return [a for a in self.afirmaciones if not a.respaldada]

    def resumen(self) -> str:
        if not self.afirmaciones:
            return "sin datos verificables"
        malas = self.sin_respaldo
        if not malas:
            return f"{len(self.afirmaciones)}/{len(self.afirmaciones)} datos respaldados"
        detalle = ", ".join(f"{a.texto!r}" for a in malas[:4])
        return f"{len(malas)} de {len(self.afirmaciones)} datos SIN respaldo: {detalle}"


def _extraer(respuesta: str) -> list[Afirmacion]:
    afirmaciones: list[Afirmacion] = []
    vistas: set[tuple[str, str]] = set()

    for tipo, patron in PATRONES.items():
        for m in patron.finditer(respuesta):
            grupos = [g for g in m.groups() if g]
            if not grupos:
                continue
            if tipo in ("norma", "sentencia"):
                # el año de dos cifras aparece en el corpus como 4: C-535/97
                numero, anio = grupos[0], grupos[-1]
                clave = f"{numero}|{anio[-2:]}"
            else:
                clave = _normalizar(grupos[0])
            if (tipo, clave) in vistas:
                continue
            vistas.add((tipo, clave))
            afirmaciones.append(Afirmacion(tipo=tipo, texto=m.group(0).strip(), clave=clave))
    return afirmaciones


def _respaldada(afirmacion: Afirmacion, contexto: str) -> bool:
    if afirmacion.tipo in ("norma", "sentencia"):
        numero, anio2 = afirmacion.clave.split("|")
        # el número y el año deben aparecer CERCA, no sueltos por el documento:
        # un "1713" en una tabla y un "2002" en otra línea no son una cita.
        patron = re.compile(rf"{re.escape(numero)}\D{{0,20}}(?:19|20)?{re.escape(anio2)}\b")
        return bool(patron.search(contexto))
    return afirmacion.clave in contexto


def _frases(respuesta: str) -> list[str]:
    partes = re.split(r"(?<=[.;:])\s+", respuesta.strip())
    return [p for p in partes if p.strip()]


def verificar(respuesta: str, fragmentos: list[dict]) -> Informe:
    """Contrasta los datos duros de `respuesta` contra el texto de `fragmentos`."""
    contexto = _normalizar(" \n ".join((f.get("texto") or "") for f in fragmentos))
    # los identificadores viven en la metadata, no siempre dentro del texto
    contexto += " " + _normalizar(
        " ".join(
            f"{f.get('identificador_documento') or ''} {f.get('titulo_documento') or ''}" for f in fragmentos
        )
    )

    informe = Informe(afirmaciones=_extraer(respuesta))
    for a in informe.afirmaciones:
        a.respaldada = _respaldada(a, contexto)

    malas = {a.texto for a in informe.sin_respaldo}
    if malas:
        for frase in _frases(respuesta):
            if any(t in frase for t in malas) and not any(m in _normalizar(frase) for m in _FRASES_META):
                informe.frases_sin_respaldo.append(frase)
    return informe


def _fragmento_citado(frase: str, fragmentos: list[dict]) -> dict | None:
    """Encuentra a qué fragmento atribuye la frase, si lo dice explícitamente."""
    frase_n = _normalizar(frase)
    for f in fragmentos:
        ident = _normalizar(f.get("identificador_documento") or "")
        if not ident or len(ident) < 4:
            continue
        if ident in frase_n:
            return f
        # "Decreto 1713 de 2002" en la respuesta vs "DECRETO-1713-2002" en la
        # metadata: comparar por los números, que es lo que no cambia
        numeros = re.findall(r"\d+", ident)
        if len(numeros) >= 2:
            patron = re.compile(rf"{numeros[0]}\D{{0,20}}{numeros[1][-2:]}\b")
            if patron.search(frase_n):
                return f
    return None


def verificar_atribucion(respuesta: str, fragmentos: list[dict]) -> Informe:
    """Comprueba que cada dato esté en el fragmento AL QUE SE LE ATRIBUYE.

    `verificar` pregunta "¿este dato está en alguna parte de lo que recibió el
    modelo?". Esto pregunta lo que de verdad importa para una cita: "¿está en el
    documento que la respuesta dice que lo dice?".

    NO usar como filtro de salida: medido sobre las mismas 150 respuestas, marca
    6 y se equivoca en 2 (precisión 67%), mientras que `verificar` marca 21 sin
    un solo falso positivo. Se conserva como diagnóstico.

    Por qué rinde menos de lo que promete, que es el hallazgo interesante: de
    104 respuestas incorrectas reales, 68 —el 65%— fallan por atribuir mal, pero
    esa mala atribución casi nunca consiste en un dato ausente del documento
    citado. Consiste en citar el artículo 38 cuando la respuesta estaba en el 39
    del MISMO decreto. Eso es un error de relevancia, no de anclaje, y ninguna
    comprobación de cadenas puede verlo: haría falta saber qué se preguntaba.
    """
    informe = Informe()
    for frase in _frases(respuesta):
        if any(m in _normalizar(frase) for m in _FRASES_META):
            continue
        citado = _fragmento_citado(frase, fragmentos)
        if citado is None:
            continue  # sin atribución explícita no hay nada que contrastar aquí
        contexto = _normalizar(citado.get("texto") or "")
        contexto += " " + _normalizar(
            f"{citado.get('identificador_documento') or ''} {citado.get('titulo_documento') or ''}"
        )
        malas_frase = []
        for a in _extraer(frase):
            # el propio identificador citado no se verifica contra sí mismo
            if a.tipo in ("norma", "sentencia") and _fragmento_citado(a.texto, [citado]):
                a.respaldada = True
            else:
                a.respaldada = _respaldada(a, contexto)
            informe.afirmaciones.append(a)
            if not a.respaldada:
                malas_frase.append(a)
        if malas_frase:
            informe.frases_sin_respaldo.append(frase)
    return informe


def marcar(respuesta: str, informe: Informe, marca: str = "⚠") -> str:
    """Devuelve la respuesta con los datos sin respaldo señalados.

    Se marca en vez de borrar: suprimir en silencio le oculta al usuario que el
    modelo afirmó algo, y verlo señalado enseña a desconfiar de la prosa y a ir
    a la cita, que es lo verificable.
    """
    salida = respuesta
    for a in informe.sin_respaldo:
        salida = salida.replace(a.texto, f"{marca}[{a.texto}: no está en las fuentes citadas]")
    return salida


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    frags = [
        {
            "texto": "Decreto 1713 de 2002, artículo 40. La recolección de residuos "
            "originados por poda de árboles se hará mediante operativos especiales.",
            "identificador_documento": "Decreto 1713 de 2002",
        }
    ]
    mala = "Según el Decreto 605 de 1996, artículo 40, la recolección se hace en 15 días."
    inf = verificar(mala, frags)
    print("anclada:", inf.anclada)
    print(inf.resumen())
    print(marcar(mala, inf))
