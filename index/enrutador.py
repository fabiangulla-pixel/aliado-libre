"""Decide si una consulta la contesta el modelo propio o una IA externa.

El modelo propio (fine-tuneado, gratis, local) responde lo sencillo. Una IA
comercial —con la clave que ponga el usuario, que no guardamos— entra solo
cuando la consulta lo justifica. Así el costo por API se concentra donde de
verdad hace falta y el servicio sigue siendo gratuito para la mayoría de casos.

La señal para decidir no es el texto de la pregunta sino **la calidad de lo
recuperado**, y hay una razón medida para ello: el modo de fallo dominante del
modelo propio no es inventar, es elegir mal el pasaje entre los que recibió.
Cuando la búsqueda trae un fragmento claramente por delante de los demás, esa
elección es fácil y el modelo propio basta. Cuando trae ocho fragmentos
igualados y mediocres, hay que discriminar de verdad, y ahí es donde el modelo
propio se equivoca.

Los umbrales de abajo son un punto de partida razonable, NO valores medidos.
Se calibran con `finetune/calibrar_abstencion.py` sobre el conjunto de
desarrollo, nunca sobre el de prueba.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Puntaje de fusión RRF mínimo del mejor fragmento para fiarse del modelo propio.
UMBRAL_PUNTAJE = float(os.environ.get("ALIADO_UMBRAL_LOCAL", "0.045"))
# Cuánto debe destacar el primero sobre el segundo para considerarlo claro.
VENTAJA_MINIMA = float(os.environ.get("ALIADO_VENTAJA_MINIMA", "1.15"))
# Por debajo de esto no hay con qué responder, venga de donde venga.
UMBRAL_ABSTENCION = float(os.environ.get("ALIADO_UMBRAL_ABSTENCION", "0.020"))


@dataclass
class Decision:
    motor: str  # "local" | "externo" | "condicional" | "abstenerse"
    motivo: str

    @property
    def responde(self) -> bool:
        """Hay respaldo claro. "condicional" NO cuenta: la cobertura medida
        (`medir_demanda_real.py`) conserva su significado."""
        return self.motor in ("local", "externo")

    @property
    def puede_redactar(self) -> bool:
        """Se puede redactar, con condiciones si es "condicional": la respuesta
        solo se muestra si pasa `index.respaldo.respaldo_suficiente`."""
        return self.motor != "abstenerse"


def _puntajes(resultados: list[dict]) -> list[float]:
    return [r.get("puntaje") or 0.0 for r in resultados]


def decidir(resultados: list[dict], hay_clave_externa: bool = False) -> Decision:
    """Elige quién contesta, a partir de lo que trajo la búsqueda."""
    if not resultados:
        return Decision("abstenerse", "La búsqueda no encontró nada en el índice.")

    puntajes = _puntajes(resultados)
    mejor = puntajes[0]
    segundo = puntajes[1] if len(puntajes) > 1 else 0.0

    # Todo lo que trajo la búsqueda ya no rige: redactar sobre eso es presentar
    # derecho muerto como respuesta. Se dice qué se encontró y por qué no sirve,
    # que es una abstención útil y no un "no sé".
    from index.vigencia import documento_no_vigente

    considerados = resultados[:5]
    if all(documento_no_vigente(r) for r in considerados):
        encontrados = "; ".join(
            f"{r.get('titulo_documento') or r.get('identificador_documento')} "
            f"({(r.get('vigencia') or {}).get('nota') or 'no vigente'})"
            for r in considerados[:3]
        )
        return Decision(
            "abstenerse",
            "Lo único que el índice tiene sobre esto son normas que ya no rigen según su "
            f"propia nota oficial: {encontrados}. Busca la norma que las reemplazó.",
        )

    if mejor < UMBRAL_ABSTENCION:
        # 29-sep-2026: el puntaje es casi binario (0,0167 si lo encontró un solo
        # motor, >=0,026 si los dos), así que este umbral mide si coinciden la
        # búsqueda léxica y la semántica, no si hay respuesta. Callar aquí dejaba
        # sin respuesta 21 de 48 consultas del piloto que el modelo respondía con
        # citas literales verificadas. Ahora se redacta y la respuesta solo se
        # muestra si pasa index.respaldo.respaldo_suficiente.
        return Decision(
            "condicional",
            "Coincidencia débil: solo un método de búsqueda encontró estos documentos.",
        )

    claro = mejor >= UMBRAL_PUNTAJE and (segundo == 0 or mejor / segundo >= VENTAJA_MINIMA)
    if claro:
        return Decision("local", "Un documento destaca con claridad: el modelo propio basta.")

    if hay_clave_externa:
        return Decision(
            "externo",
            "Varios documentos compiten y hay que discriminar entre ellos.",
        )
    return Decision(
        "local",
        "Consulta difícil y sin clave de IA externa configurada: responde el modelo "
        "propio, con menos confianza.",
    )


def mensaje_abstencion(total_fragmentos: int | None = None, fuentes: int = 7) -> str:
    """Explica por qué no se responde, distinguiendo 'no está' de 'no sé'.

    Un vacío de cobertura declarado es información útil; un "no sé" pelado
    parece incompetencia y no le sirve a nadie.
    """
    alcance = (
        f"Busqué en {total_fragmentos:,} fragmentos de {fuentes} fuentes oficiales."
        if total_fragmentos
        else f"Busqué en el índice completo ({fuentes} fuentes oficiales)."
    ).replace(",", ".")
    return (
        f"No encontré nada suficientemente cercano a tu consulta. {alcance}\n\n"
        "Ten en cuenta dos huecos conocidos de cobertura: el Consejo de Estado no está "
        "en el índice porque su portal bloquea el acceso automatizado, y la Corte Suprema "
        "tampoco porque su servidor de consulta lleva meses fallando. Además el índice es "
        "una instantánea: no refleja normas ni sentencias posteriores a su última "
        "actualización.\n\n"
        "Prueba a reformular con los términos que usaría la norma "
        "(por ejemplo «terminación unilateral del contrato» en vez de «me echaron»)."
    )
