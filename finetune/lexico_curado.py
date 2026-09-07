"""Puente entre cómo pregunta la gente y cómo se llama eso en la norma.

Escrito a mano, y a propósito. Se intentó minarlo de los 936 pares del banco
(`finetune/minar_lexico.py`) y el resultado fue ruido: "plata -> 2555,
efectivamente, regulado". Con novecientos ejemplos repartidos por todo el derecho
colombiano, la información mutua no distingue señal de casualidad, y las palabras
coloquiales más frecuentes ("puedo", "necesito") no tienen contraparte jurídica.
El paper del que viene la idea (arXiv 2609.01645) tampoco lo minó: su puente
también era curado, para 25 necesidades concretas.

Criterio de qué entra aquí: solo lo que una persona diría de verdad y que **no
aparece** en el texto de la norma que lo regula. "Despido" no entra: la norma
también dice despido. "Me echaron" sí.

Cada entrada es una apuesta comprobable, y se comprueba en datos apartados:
si el puente no sube el acierto, se tira, no se defiende.
"""

from __future__ import annotations

# Términos coloquiales -> cómo lo nombra la norma colombiana.
# Las traducciones se AÑADEN a la consulta léxica, no sustituyen: la palabra
# original puede ser la buena, y quitarla sería apostar a ciegas.
PUENTE: dict[str, tuple[str, ...]] = {
    # trabajo
    "echaron": ("despido", "terminacion unilateral", "contrato"),
    "echar": ("despido", "terminacion"),
    "botaron": ("despido", "terminacion unilateral"),
    "botar": ("despido", "terminacion"),
    "sacaron": ("despido", "terminacion"),
    "renuncie": ("renuncia", "terminacion voluntaria"),
    "sueldo": ("salario", "remuneracion"),
    "plata": ("dinero", "suma", "pago"),
    "jefe": ("empleador", "patrono"),
    "trabajador": ("empleado", "servidor"),
    "incapacitado": ("incapacidad", "estabilidad laboral reforzada"),
    "embarazada": ("fuero de maternidad", "estabilidad laboral reforzada", "licencia"),
    "prima": ("prestaciones sociales", "prima de servicios"),
    "liquidacion": ("prestaciones sociales", "cesantias", "indemnizacion"),
    # vivienda y servicios
    "arriendo": ("arrendamiento", "canon"),
    "casero": ("arrendador",),
    "inquilino": ("arrendatario",),
    "recibo": ("factura", "facturacion"),
    "luz": ("energia electrica", "servicio publico domiciliario"),
    "agua": ("acueducto", "servicio publico domiciliario"),
    "basura": ("aseo", "residuos solidos"),
    "cobran": ("cobro", "facturacion", "tarifa"),
    # salud y pensión
    "eps": ("entidad promotora de salud", "sistema de seguridad social"),
    "pension": ("pension", "prestacion economica", "regimen pensional"),
    "jubilacion": ("pension de vejez",),
    "medicamento": ("suministro", "prestacion asistencial"),
    "cita": ("atencion", "servicio de salud"),
    # trámites y reclamos
    "demandar": ("demanda", "accion judicial", "proceso"),
    "denunciar": ("denuncia", "querella"),
    "reclamar": ("reclamacion", "peticion", "recurso"),
    "queja": ("reclamacion", "peticion", "recurso de reposicion"),
    "papeles": ("documentos", "requisitos"),
    "tramite": ("procedimiento", "actuacion administrativa"),
    "multa": ("sancion", "comparendo"),
    "estafa": ("estafa", "fraude", "engano"),
    # negocios
    "negocio": ("establecimiento de comercio", "actividad mercantil"),
    "socio": ("socio", "accionista"),
    "empresa": ("sociedad", "persona juridica"),
    "impuesto": ("tributo", "obligacion tributaria"),
    "factura": ("factura", "documento equivalente"),
    "deuda": ("obligacion", "acreencia"),
    "cobrador": ("acreedor", "cobranza"),
    # familia
    "divorcio": ("cesacion de efectos civiles", "disolucion"),
    "hijos": ("menores", "custodia", "alimentos"),
    "cuota": ("alimentos", "cuota alimentaria"),
    "herencia": ("sucesion", "herederos"),
}


def expandir(tokens: list[str]) -> list[str]:
    """Añade a los tokens de la consulta los términos jurídicos equivalentes.

    Devuelve la lista original seguida de lo añadido, sin repetir. El orden
    importa poco para FTS5 pero se conserva para que sea legible al depurar.
    """
    vistos = set(tokens)
    salida = list(tokens)
    for token in tokens:
        for traduccion in PUENTE.get(token, ()):
            for palabra in traduccion.split():
                if palabra not in vistos:
                    vistos.add(palabra)
                    salida.append(palabra)
    return salida
