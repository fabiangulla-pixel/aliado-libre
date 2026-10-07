"""Búsqueda asistida por LLM: reformula la consulta y reordena los candidatos.

Medido el 3-oct-2026 sobre el banco piloto (`finetune/eval/reordenar_amplio.py`):
con Sonnet 5, recall@5 27,4% -> 47,4% (dev 50,0%, prueba 45,1%; gana 26 casos,
pierde 7, p≈0,001). Es la primera técnica de recuperación que mejora en datos
apartados; HyDE, el puente de vocabulario, el embedding afinado y el
cross-encoder no lo hicieron. Haiku 4.5 NO sirve para esto (27,3%): por eso el
modelo por defecto no es el de redactar.

Dos llamadas al modelo por búsqueda:
1. Tres reformulaciones de la pregunta en el vocabulario de la norma. Cada una
   se busca con los dos motores y sus listas se fusionan con las de la original.
2. El modelo ve un fragmento por documento (los primeros `DOCUMENTOS`) y elige
   los 10 que mejor responden.

Si cualquier paso falla, quien llama recibe la excepción y sigue con la búsqueda
normal: esto mejora el orden, nunca es condición para buscar.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

MODELO_DEFECTO = "claude-sonnet-5"
REFORMULACIONES = 3
N_MOTOR = 120
DOCUMENTOS = int(os.environ.get("ALIADO_ASISTIDA_DOCUMENTOS", "60"))
EXTRACTO = 400
ELEGIDOS = 10
PESO_LEXICO = 0.8  # mismo peso que la fusión de producción
K_RRF = 60

SISTEMA_REESCRIBIR = f"""Eres un abogado colombiano. Una persona sin formación jurídica \
describe un problema con sus palabras. Escribe {REFORMULACIONES} reformulaciones de su \
pregunta como las buscaría un abogado en la legislación y la jurisprudencia \
colombianas: con el vocabulario de la norma, la figura jurídica y la rama del \
derecho que aplica. Cada una en una línea, sin numerar, sin explicar. No inventes \
números de ley, de artículo ni de sentencia: un número inventado lleva la búsqueda \
al documento equivocado."""

SISTEMA_ORDENAR = f"""Eres un abogado colombiano que ayuda a una persona sin formación \
jurídica a encontrar la norma que responde su pregunta. Recibes la pregunta, escrita \
como la escribe la persona, y una lista numerada de documentos candidatos (título y un \
extracto). Elige los {ELEGIDOS} documentos que MEJOR responden la pregunta, del más útil \
al menos útil. Piensa en qué problema jurídico describe realmente la persona aunque no \
use el vocabulario jurídico. Prefiere la norma que regula el asunto sobre la que solo \
lo menciona. Responde SOLO con los números separados por comas."""


@dataclass
class ResultadoAsistido:
    resultados: list[dict]
    usd: float = 0.0
    reformulaciones: list[str] = field(default_factory=list)


def activa() -> bool:
    """Encendida por variable de entorno; el modo público la enciende en su script."""
    return os.environ.get("ALIADO_BUSQUEDA_ASISTIDA", "").strip() == "1"


def modelo() -> str:
    return os.environ.get("ALIADO_ASISTIDA_MODELO", "").strip() or MODELO_DEFECTO


def _llamar(cliente, nombre_modelo: str, sistema: str, texto: str):
    config = (
        {}
        if nombre_modelo.startswith("claude-haiku")
        else {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "low"},
        }
    )
    msg = cliente.messages.create(
        model=nombre_modelo,
        max_tokens=8000,
        system=sistema,
        messages=[{"role": "user", "content": texto}],
        **config,
    )
    if msg.stop_reason == "refusal":
        raise RuntimeError("El modelo declinó la petición.")
    salida = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    return salida, msg.usage


def fusionar(listas: list[list[str]]) -> list[str]:
    """RRF sobre pares (vectorial, léxica) de listas de ids."""
    puntaje: dict[str, float] = {}
    for i, lista in enumerate(listas):
        peso = 1.0 if i % 2 == 0 else PESO_LEXICO
        for rango, frag in enumerate(lista):
            puntaje[frag] = puntaje.get(frag, 0) + peso / (K_RRF + rango)
    return [f for f, _ in sorted(puntaje.items(), key=lambda x: -x[1])]


def documento_de(frag_id: str) -> str:
    return frag_id.rsplit("::", 1)[0]


def un_fragmento_por_documento(orden: list[str], n: int) -> list[str]:
    vistos: set[str] = set()
    salida: list[str] = []
    for frag in orden:
        doc = documento_de(frag)
        if doc not in vistos:
            vistos.add(doc)
            salida.append(frag)
            if len(salida) == n:
                break
    return salida


def interpretar(texto: str, n: int) -> list[int]:
    elegidos: list[int] = []
    for m in re.findall(r"\d+", texto or ""):
        i = int(m)
        if 1 <= i <= n and i not in elegidos:
            elegidos.append(i)
    return elegidos[:ELEGIDOS]


def buscar_asistida(indice, consulta: str, k: int, clave: str) -> ResultadoAsistido:
    """Devuelve los k mejores resultados con el mismo formato que `IndiceBusqueda.buscar`.

    `indice` es un `IndiceBusqueda` local: hace falta acceso a los dos motores.
    """
    import anthropic

    from index import costos
    from index.vigencia import anotar

    nombre = modelo()
    cliente = anthropic.Anthropic(api_key=clave)
    usd = 0.0

    texto, uso = _llamar(cliente, nombre, SISTEMA_REESCRIBIR, consulta)
    usd += costos.liquidar(uso, nombre).usd
    reformulaciones = [x.strip(" -•") for x in texto.splitlines() if x.strip()][:REFORMULACIONES]
    # El prompt pide no inventar números de norma; esto lo garantiza (fallo de HyDE).
    from index.salvaguardas import quitar_numeros_inventados

    reformulaciones = [r for r in (quitar_numeros_inventados(x, consulta) for x in reformulaciones) if r]

    listas = indice.listas_candidatos(consulta, N_MOTOR)
    for r in reformulaciones:
        listas += indice.listas_candidatos(r, N_MOTOR)
    orden = fusionar(listas)
    pool = un_fragmento_por_documento(orden, DOCUMENTOS)
    if not pool:
        return ResultadoAsistido([], usd, reformulaciones)

    datos = indice._coleccion.get(ids=pool, include=["documents", "metadatas"])
    textos = dict(zip(datos["ids"], datos["documents"], strict=True))
    metas = dict(zip(datos["ids"], datos["metadatas"], strict=True))
    lineas = []
    for i, f in enumerate(pool, 1):
        titulo = (metas.get(f) or {}).get("titulo_documento") or documento_de(f)
        extracto = re.sub(r"\s+", " ", textos.get(f) or "")[:EXTRACTO]
        lineas.append(f"[{i}] {titulo}\n{extracto}")
    prompt = f"Pregunta: {consulta}\n\nDocumentos:\n\n" + "\n\n".join(lineas) + f"\n\nLos {ELEGIDOS} mejores:"
    texto, uso = _llamar(cliente, nombre, SISTEMA_ORDENAR, prompt)
    usd += costos.liquidar(uso, nombre).usd

    elegidos = [pool[i - 1] for i in interpretar(texto, len(pool))]
    finales = (elegidos + [f for f in pool if f not in elegidos])[:k]
    resultados = []
    for posicion, f in enumerate(finales):
        if f not in textos:
            continue
        resultados.append(
            {
                "id": f,
                # No es un puntaje RRF: el orden lo puso el modelo. Se deja
                # decreciente para que quien ordene por puntaje respete ese orden.
                "puntaje": round(1.0 / (1 + posicion), 4),
                "texto": textos[f],
                **(metas.get(f) or {}),
            }
        )
    return ResultadoAsistido(anotar(resultados), usd, reformulaciones)
