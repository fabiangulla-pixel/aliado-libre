"""Borradores de escritos para el ciudadano: derecho de petición, reclamo a una
empresa de servicios públicos, reclamación directa al proveedor y tutela.

La búsqueda le dice a la persona qué norma la protege; esto responde a la
pregunta siguiente, «¿y ahora qué hago?», con un documento que puede presentar.

Decisiones (27-nov-2026), y no son de estilo:

1. **Sin IA.** El escrito se arma con plantilla: los hechos son los que escribe
   la persona, tal cual; el fundamento son las normas que ELLA eligió de los
   resultados, con su texto literal. Un modelo que «mejore» los hechos puede
   inventar uno, y en un documento que se firma eso es lo peor que puede pasar.
   Además cuesta cero, así que no gasta la cuota de redacciones.
2. **Lo que no se sabe queda en blanco y a la vista** ([Tu nombre completo],
   [Número de cédula]…). No se piden datos personales: no pasan por el servidor
   y la persona los escribe en su copia.
3. **Las normas fijas de cada plantilla** (art. 23 de la Constitución, Ley 1755
   de 2015…) son la base procesal del escrito y se declaran como tales; las del
   fundamento salen de la búsqueda y se verifican como literales.
4. **No se guarda nada.** El servidor arma el texto y lo devuelve.

No es asesoría: cada borrador lo dice en su primera línea de avisos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from index.respaldo import normalizar

MAX_HECHOS = 6000
MAX_PETICIONES = 3000
MAX_FUNDAMENTOS = 5
MAX_CITA = 1200
MAX_CAMPO = 200

MESES = ("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre").split()


@dataclass(frozen=True)
class Plantilla:
    clave: str
    nombre: str
    titulo: str
    destinatario_defecto: str
    base_legal: str  # párrafo fijo: base procesal de este escrito
    peticiones_defecto: tuple[str, ...]
    cierre: str
    avisos: tuple[str, ...]
    juramento: str = ""
    # Plazo general de respuesta en días hábiles, para calcular la fecha con
    # index/plazos.py (27-nov-2026). None = no hay un plazo único que decir.
    plazo_dias_habiles: int | None = None


PLANTILLAS: dict[str, Plantilla] = {
    p.clave: p
    for p in (
        Plantilla(
            clave="peticion",
            plazo_dias_habiles=15,
            nombre="Derecho de petición",
            titulo="DERECHO DE PETICIÓN",
            destinatario_defecto="[Nombre de la entidad o empresa a la que te diriges]",
            base_legal=(
                "Presento esta petición en ejercicio del derecho fundamental consagrado en el artículo 23 "
                "de la Constitución Política y regulado por la Ley 1755 de 2015, que sustituyó el Título II "
                "del Código de Procedimiento Administrativo y de lo Contencioso Administrativo (Ley "
                "1437 de 2011)."
            ),
            peticiones_defecto=(
                "[Escribe aquí, en concreto, qué pides: información, copia de un documento, una actuación…]",
                "Que se me dé respuesta de fondo, clara y congruente con lo pedido, dentro del término "
                "legal.",
            ),
            cierre="Recibiré respuesta en la dirección física o el correo electrónico indicados abajo.",
            avisos=(
                "Por regla general, la respuesta debe darse dentro de los 15 días hábiles siguientes a la "
                "recepción (Ley 1755 de 2015, art. 14); hay plazos distintos para documentos e información y "
                "para consultas. Verifica el que aplica a tu caso.",
                "Guarda la constancia de radicación (número y fecha): la necesitas si no te responden.",
            ),
        ),
        Plantilla(
            clave="servicios",
            plazo_dias_habiles=15,
            nombre="Reclamo a la empresa de servicios públicos",
            titulo="RECLAMO ANTE LA EMPRESA DE SERVICIOS PÚBLICOS DOMICILIARIOS",
            destinatario_defecto="[Nombre de la empresa de energía, agua, gas, aseo o telefonía fija]",
            base_legal=(
                "Presento este reclamo con fundamento en el artículo 23 de la Constitución Política y en la "
                "Ley 142 de 1994, que en sus artículos 152 y siguientes reconoce a los suscriptores y "
                "usuarios "
                "el derecho a presentar peticiones, quejas y recursos ante la empresa prestadora."
            ),
            peticiones_defecto=(
                "[Escribe aquí qué pides: revisar la factura del periodo ___, reconectar el servicio, "
                "devolver un cobro…]",
                "Que se me dé respuesta de fondo dentro del término legal.",
            ),
            cierre=(
                "Número de cuenta o contrato: [__________]. Dirección del inmueble: [__________]. "
                "Recibiré respuesta en la dirección o el correo indicados abajo."
            ),
            avisos=(
                "La Ley 142 de 1994 (art. 158) fija un plazo de 15 días hábiles para que la empresa "
                "responda; "
                "si no responde a tiempo, puede operar el silencio administrativo positivo. Verifica las "
                "condiciones en la norma.",
                "Si la respuesta no te satisface, contra la decisión proceden los recursos de "
                "reposición ante la "
                "empresa y, en subsidio, de apelación ante la Superintendencia de Servicios Públicos "
                "Domiciliarios. Revisa el plazo para interponerlos en la respuesta que recibas.",
            ),
        ),
        Plantilla(
            clave="consumidor",
            nombre="Reclamación directa al proveedor (consumidor)",
            titulo="RECLAMACIÓN DIRECTA AL PRODUCTOR O PROVEEDOR",
            destinatario_defecto="[Nombre del almacén, tienda en línea, banco o empresa que te vendió]",
            base_legal=(
                "Presento esta reclamación en mi calidad de consumidor, con fundamento en el artículo "
                "78 de la "
                "Constitución Política y en la Ley 1480 de 2011 (Estatuto del Consumidor)."
            ),
            peticiones_defecto=(
                "[Escribe aquí qué pides: hacer efectiva la garantía, cambiar el producto, devolver el "
                "dinero, "
                "entregar lo comprado…]",
                "Que se me responda por escrito.",
            ),
            cierre=(
                "Datos de la compra: fecha [__________], número de factura o pedido [__________], valor "
                "pagado "
                "[__________]. Recibiré respuesta en la dirección o el correo indicados abajo."
            ),
            avisos=(
                "Guarda la factura, el pedido y la constancia de que enviaste esta reclamación: la "
                "reclamación "
                "directa al proveedor suele ser el paso previo para acudir a la Superintendencia de "
                "Industria y "
                "Comercio.",
                "Si no te responden o no quedas satisfecho, puedes acudir a la Superintendencia de "
                "Industria y "
                "Comercio. Verifica en su sitio el trámite vigente.",
            ),
        ),
        Plantilla(
            clave="tutela",
            nombre="Acción de tutela",
            titulo="ACCIÓN DE TUTELA",
            destinatario_defecto="Señor(a) Juez de la República (reparto)",
            base_legal=(
                "Presento esta acción de tutela con fundamento en el artículo 86 de la Constitución "
                "Política y "
                "en el Decreto 2591 de 1991, para la protección inmediata de mis derechos fundamentales."
            ),
            peticiones_defecto=(
                "Que se tutelen mis derechos fundamentales a [__________].",
                "Que se ordene a [entidad o persona accionada] que, en el término que el despacho fije, "
                "[__________].",
            ),
            cierre=(
                "Accionado: [Nombre de la entidad o persona contra la que presentas la tutela], dirección de "
                "notificación [__________]. Derechos fundamentales vulnerados: [__________]."
            ),
            juramento=(
                "Manifiesto bajo la gravedad del juramento que no he presentado otra acción de tutela "
                "por los "
                "mismos hechos y derechos."
            ),
            avisos=(
                "La tutela procede cuando no tienes otro medio de defensa judicial eficaz, o para evitar un "
                "perjuicio irremediable. Si el problema se resuelve con un derecho de petición o un reclamo, "
                "empieza por ahí: muchas tutelas se niegan por no haberlo intentado.",
                "Por regla general el juez debe decidir dentro de los 10 días siguientes a la presentación "
                "(Constitución, art. 86).",
            ),
        ),
    )
}

AVISO_GENERAL = (
    "Este es un BORRADOR orientativo, no asesoría jurídica. Revisa cada dato, completa lo que está entre "
    "corchetes y, si puedes, muéstraselo a un consultorio jurídico gratuito o a la Defensoría del Pueblo "
    "antes de presentarlo."
)


class ErrorEscrito(ValueError):
    pass


def _limpio(valor, maximo: int) -> str:
    if not isinstance(valor, str):
        return ""
    # Fuera los caracteres de control (salvo saltos de línea y tabuladores).
    valor = "".join(c for c in valor if c in "\n\t" or ord(c) >= 32)
    return valor.strip()[:maximo]


def _parrafos(texto: str) -> list[str]:
    """Separa por líneas en blanco o por líneas; quita viñetas y numeración
    que ya traiga, para numerar parejo."""
    bloques = [b.strip() for b in re.split(r"\n\s*\n", texto) if b.strip()]
    if len(bloques) == 1:
        bloques = [b.strip() for b in texto.split("\n") if b.strip()]
    return [re.sub(r"^\s*(?:[-*•]|\d+[.)-]|[a-z][.)])\s*", "", b) for b in bloques]


def fecha_larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _fundamento(f: dict) -> tuple[str, str | None]:
    """(texto del fundamento, aviso o None). La cita se comprueba contra el
    fragmento que la acompaña: si no está literal, se dice."""
    titulo = _limpio(f.get("titulo"), MAX_CAMPO) or _limpio(f.get("identificador"), MAX_CAMPO)
    if not titulo:
        return "", None
    cita = _limpio(f.get("cita"), MAX_CITA)
    fuente = _limpio(f.get("texto_fuente"), 20000)
    url = _limpio(f.get("url"), 500)
    linea = titulo
    if url.startswith(("http://", "https://")):
        linea += f" (texto oficial: {url})"
    if not cita:
        return linea + ".", None
    aviso = None
    if fuente and normalizar(cita) not in normalizar(fuente):
        aviso = (
            f"La cita de «{titulo}» no coincide literalmente con el texto encontrado: "
            "compárala con la fuente."
        )
    return f"{linea}, que dispone: «{cita}».", aviso


def armar(datos: dict, hoy: date | None = None) -> dict:
    """{"titulo", "texto", "avisos"} o ErrorEscrito con un mensaje para la persona."""
    tipo = _limpio(datos.get("tipo"), 40)
    plantilla = PLANTILLAS.get(tipo)
    if plantilla is None:
        raise ErrorEscrito(f"Tipo de escrito desconocido. Disponibles: {', '.join(PLANTILLAS)}.")
    hechos = _limpio(datos.get("hechos"), MAX_HECHOS)
    if len(hechos) < 20:
        raise ErrorEscrito("Cuenta los hechos: qué pasó, cuándo y con quién (al menos una o dos frases).")

    destinatario = _limpio(datos.get("destinatario"), MAX_CAMPO) or plantilla.destinatario_defecto
    ciudad = _limpio(datos.get("ciudad"), 80) or "[Ciudad]"
    peticiones_usuario = _parrafos(_limpio(datos.get("peticiones"), MAX_PETICIONES))
    peticiones = peticiones_usuario or list(plantilla.peticiones_defecto)

    avisos = [AVISO_GENERAL, *plantilla.avisos]
    fundamentos = []
    for f in (datos.get("fundamentos") or [])[:MAX_FUNDAMENTOS]:
        if isinstance(f, dict):
            texto, aviso = _fundamento(f)
            if texto:
                fundamentos.append(texto)
            if aviso:
                avisos.append(aviso)
    if not fundamentos:
        avisos.append(
            "No elegiste normas de los resultados: el escrito solo trae la base legal general. Si la "
            "búsqueda "
            "encontró la norma de tu caso, márcala para que quede citada."
        )

    hoy = hoy or date.today()
    plazo = None
    if plantilla.plazo_dias_habiles:
        from index.plazos import vencimiento

        plazo = vencimiento(hoy, plantilla.plazo_dias_habiles)
        avisos.insert(
            1,
            f"Si lo radicas hoy, el plazo general de {plantilla.plazo_dias_habiles} días hábiles para "
            f"responderte vence el {plazo['vence_texto']}. Si lo radicas otro día, recalcula con la "
            "calculadora de plazos.",
        )
    lineas = [
        f"{ciudad}, {fecha_larga(hoy)}",
        "",
        *([] if destinatario.lower().startswith("señor") else ["Señores"]),
        destinatario,
        "[Dirección o correo de radicación]",
        "",
        f"Asunto: {plantilla.titulo}",
        "",
        "Yo, [Tu nombre completo], identificado(a) con cédula de ciudadanía n.º [__________] de "
        "[__________], "
        "me dirijo a ustedes de manera respetuosa para presentar el siguiente escrito.",
        "",
        "HECHOS",
        "",
    ]
    lineas += [f"{i}. {p}" for i, p in enumerate(_parrafos(hechos), 1)]
    lineas += ["", "FUNDAMENTOS DE DERECHO", "", plantilla.base_legal]
    if fundamentos:
        lineas += ["", "Además, son aplicables:"]
        lineas += [f"- {f}" for f in fundamentos]
    lineas += ["", "PETICIONES", ""]
    lineas += [f"{i}. {p}" for i, p in enumerate(peticiones, 1)]
    if plantilla.juramento:
        lineas += ["", "JURAMENTO", "", plantilla.juramento]
    lineas += [
        "",
        "ANEXOS",
        "",
        "[Enumera las copias que adjuntas: factura, contrato, fotos, respuestas anteriores…]",
        "",
        "NOTIFICACIONES",
        "",
        plantilla.cierre,
        "Dirección: [__________]. Correo electrónico: [__________]. Teléfono: [__________].",
        "",
        "Atentamente,",
        "",
        "",
        "______________________________",
        "[Tu nombre completo]",
        "C.C. [__________]",
    ]
    return {"titulo": plantilla.nombre, "texto": "\n".join(lineas), "avisos": avisos, "plazo": plazo}


def catalogo() -> list[dict]:
    """Lo que la página necesita para ofrecer las plantillas."""
    return [{"clave": p.clave, "nombre": p.nombre} for p in PLANTILLAS.values()]
