"""Genera finetune/data/entrenamiento.jsonl a partir de finetune/data/muestra_filtrada.json.

Cada ejemplo es (pregunta, fragmento real del índice, respuesta ideal
redactada a mano, con cita exacta a la norma/sentencia/concepto de origen).
Incluye ejemplos negativos deliberados (fragmento que NO responde la
pregunta) para enseñar el comportamiento de "no inventar" — la regla más
importante del proyecto.

Formato de salida: una línea JSON por ejemplo, con el mismo prompt que usa
index/responder.py en producción (mismo PROMPT_SISTEMA), para que el modelo
entrenado responda igual de bien cuando responder.py lo invoque después."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from index.responder import PROMPT_SISTEMA, _formatear_fragmentos

RAIZ = Path(__file__).resolve().parent
MUESTRA = json.loads((RAIZ / "data" / "muestra_filtrada.json").read_text(encoding="utf-8"))


def _fragmento_como_resultado(item: dict) -> dict:
    return {
        "titulo_documento": item["meta"].get("titulo_documento")
        or item["meta"].get("identificador_documento"),
        "fuente": item["fuente"],
        "identificador_documento": item["meta"].get("identificador_documento"),
        "texto": item["texto"],
    }


# (índice en muestra_filtrada.json, pregunta, respuesta ideal)
EJEMPLOS_POSITIVOS = [
    (
        0,
        "¿Qué requisito deben cumplir los títulos obtenidos en el exterior para tener validez en Colombia?",
        "Según el Decreto 1083 de 2015 (art. 2.2.2.3.4), los estudios y títulos obtenidos en el exterior requieren, "
        "para su validez, homologación y convalidación por parte del Ministerio de Educación Nacional o la autoridad "
        "competente. Quien tome posesión de un empleo público que exija ese título puede acreditarlo primero con el "
        "certificado de la institución extranjera, pero debe presentar el título homologado dentro de los 2 años "
        "siguientes a la posesión; si no lo hace, se aplica el artículo 5 de la Ley 190 de 1995.",
    ),
    (
        1,
        "¿Quién debe verificar los antecedentes fiscales, disciplinarios y judiciales de un aspirante antes de "
        "nombrarlo en un empleo público?",
        "Según el Decreto 1083 de 2015 (art. 2.2.5.1.5), corresponde al jefe de la unidad de personal, o quien haga "
        "sus veces, verificar y certificar el cumplimiento de requisitos y competencias, y verificar directamente los "
        "antecedentes fiscales, disciplinarios y judiciales del aspirante, dejando las constancias respectivas, antes "
        "de que se efectúe el nombramiento.",
    ),
    (
        2,
        "¿Qué requisitos se le exigen a un servidor del nivel asistencial vinculado antes de 2005 si concursa por "
        "el mismo cargo?",
        "Según el Decreto 1083 de 2015 (art. 2.2.2.4.11), a los servidores del nivel asistencial y técnico vinculados "
        "antes de los Decretos 770 y 785 de 2005 que concursen para el mismo empleo en que fueron vinculados, se les "
        "exigen los mismos requisitos que estaban vigentes al momento de su vinculación.",
    ),
    (
        3,
        "¿Qué debe declarar una persona antes de tomar posesión de un empleo público?",
        "Según el Decreto 1083 de 2015 (art. 2.2.5.1.9), antes de la posesión debe declarar bajo juramento el monto "
        "de sus bienes y rentas en el formato del SIGEP, y también diligenciar el formato de hoja de vida adoptado "
        "por el Departamento Administrativo de la Función Pública a través del mismo sistema.",
    ),
    (
        4,
        "¿Quién verifica el cumplimiento de los lineamientos para elaborar los manuales específicos de entidades "
        "con sistemas especiales de nomenclatura?",
        "Según el Decreto 1083 de 2015 (art. 2.2.2.7.1), corresponde al jefe de personal, o quien haga sus veces, "
        "efectuar la verificación del cumplimiento de lo dispuesto para elaborar, actualizar o modificar los manuales "
        "específicos de las entidades con sistemas especiales.",
    ),
    (
        5,
        "¿Qué experiencia profesional se exige para el grado 1 del nivel directivo?",
        "Según el Decreto 1083 de 2015 (art. 2.2.2.8.3), para el grado 1 del nivel directivo se exige título "
        "profesional, título de posgrado en la modalidad de especialización y cuarenta y cuatro (44) meses de "
        "experiencia profesional relacionada.",
    ),
    (
        6,
        '¿Qué se entiende por "estudios" según el Decreto 1083 de 2015?',
        "Según el Decreto 1083 de 2015 (art. 2.2.2.3.2), se entienden por estudios los conocimientos académicos "
        "adquiridos en instituciones públicas o privadas reconocidas por el Gobierno Nacional, correspondientes a "
        "educación básica primaria, básica secundaria, media vocacional, superior (pregrado) y posgrado "
        "(especialización, maestría, doctorado y posdoctorado).",
    ),
    (
        7,
        "¿Quiénes integran la Mesa de Negociación de las organizaciones sindicales de empleados públicos según el "
        "Decreto 1083 de 2015?",
        "Según el Decreto 1083 de 2015 (art. 2.2.1.4.4), la Mesa está integrada por el Ministro del Trabajo (o su "
        "delegado, quien la preside), el Ministro de Hacienda y Crédito Público (o su delegado), el Director del "
        "Departamento Administrativo de la Función Pública (o su delegado), el Director del Departamento Nacional de "
        "Planeación (o su delegado), y veinte representantes de las organizaciones sindicales firmantes del Acuerdo "
        "de Negociación Colectiva de 2021.",
    ),
    (
        8,
        "¿Qué experiencia se exige para el grado 01 del nivel asesor?",
        "Según el Decreto 1083 de 2015 (art. 2.2.2.9.4), para el grado 01 del nivel asesor se exige título "
        "profesional, título de posgrado en la modalidad de especialización y veintiséis (26) meses de experiencia "
        "profesional relacionada.",
    ),
    (
        9,
        "¿Qué pasa si un empleo tiene requisitos establecidos directamente en la Constitución o la ley?",
        "Según el Decreto 1083 de 2015 (art. 2.2.2.8.9), para el ejercicio de los empleos que tengan requisitos "
        "establecidos en la Constitución Política o en la ley, se acreditarán los allí señalados — es decir, esos "
        "requisitos prevalecen sobre los requisitos generales del decreto.",
    ),
    (
        10,
        "¿Cómo define el Decreto 1083 de 2015 las competencias laborales de un empleado público?",
        "Según el Decreto 1083 de 2015 (art. 2.2.4.2), las competencias laborales se definen como la capacidad de "
        "una persona para desempeñar, en diferentes contextos y con base en los requerimientos de calidad y "
        "resultados esperados en el sector público, las funciones inherentes a un empleo, capacidad determinada por "
        "conocimientos, destrezas, habilidades, valores, actitudes y aptitudes.",
    ),
    (
        11,
        "¿Es necesario sustentar el recurso de impugnación contra un fallo de tutela de primera instancia?",
        "Según el Auto 017/94 de la Corte Constitucional, no: la Corte ha sentado posición en el sentido de que la "
        "sustentación del recurso no es un requisito indispensable para que proceda la impugnación contra los fallos "
        "de primera instancia en acciones de tutela.",
    ),
    (
        12,
        "¿Qué debe hacer un juez de tutela que se considera incompetente para conocer del caso?",
        "Según el Auto 046/96 de la Corte Constitucional, si un juez o tribunal que conoce de una tutela en primera "
        "instancia se declara incompetente, el procedimiento correcto no es negar o rechazar la demanda, sino "
        "remitir la actuación al juez que considere competente.",
    ),
    (
        13,
        "¿Qué ocurre si un juez de tutela ordena cesar la acción en vez de dictar sentencia de fondo?",
        "Según el Auto 047/95 de la Corte Constitucional, se declaró la nulidad de esa providencia, porque el juez "
        "debió fallar de fondo y no hacerlo violó el debido proceso; la Corte ordenó devolver el expediente para que "
        "se profiera el fallo correspondiente.",
    ),
    (
        14,
        "¿Puede una entidad sustituir la respuesta a un derecho de petición con el silencio administrativo "
        "negativo?",
        "Según el Auto 043/96 de la Corte Constitucional, no: el derecho de petición exige una respuesta pronta y "
        "sustancial, que no puede sustituirse por el acto ficto derivado del silencio administrativo negativo; esta "
        "es doctrina constitucional de obligatorio cumplimiento.",
    ),
    (
        15,
        "¿Qué pasa si un juzgado no notifica a un tercero con interés legítimo en una tutela?",
        "Según el Auto 040/95 de la Corte Constitucional, no notificar a personas con interés legítimo en el "
        "resultado de un proceso de tutela, aunque no hayan sido demandadas, constituye una violación al debido "
        "proceso y da lugar a la nulidad de todo lo actuado, debiendo repetirse la primera instancia.",
    ),
    (
        16,
        "¿Es obligatorio para la Sala de Selección de la Corte Constitucional motivar por qué no escoge un "
        "expediente de tutela para revisión?",
        "Según el Auto 032/95 de la Corte Constitucional, no: la revisión de fallos de tutela por la Corte es "
        "eventual y discrecional de la Sala de Selección; no hay necesidad de motivar la escogencia de los fallos "
        "que se revisan ni los que se excluyen, y ese auto no es susceptible de recursos.",
    ),
    (
        17,
        "¿Una sentencia de exequibilidad dictada bajo la Constitución de 1886 impide un nuevo estudio de "
        "constitucionalidad bajo la Constitución de 1991?",
        "Según el Auto 012/92 de la Corte Constitucional, no: aunque exista una sentencia previa de exequibilidad de "
        "la Corte Suprema sobre una norma bajo la Constitución de 1886, la cosa juzgada de esa sentencia no tiene "
        "valor respecto de la nueva Constitución de 1991, por lo que la Corte puede adelantar un nuevo estudio.",
    ),
    (
        18,
        "¿Está la Federación Nacional de Cafeteros obligada a atender las citaciones del Congreso sobre el "
        "manejo de recursos públicos del Fondo Nacional del Café?",
        "Según el Auto 023/92 de la Corte Constitucional, sí: la Federación Nacional de Cafeteros, en su condición "
        "de persona jurídica, está obligada a atender las citaciones e interrogantes de las comisiones permanentes "
        "del Congreso sobre hechos relacionados con la administración de esos recursos públicos.",
    ),
    (
        19,
        "¿Puede un tribunal rechazar por improcedente la impugnación de un fallo de tutela?",
        "Según el Auto 019/94 de la Corte Constitucional, no: el juez de tutela debe darle trámite a la impugnación "
        "y remitir el expediente al superior jerárquico, en aplicación del principio de doble instancia.",
    ),
    (
        20,
        "¿Qué consecuencia tiene que un juez no notifique a una de las partes contra quien se dirige una tutela?",
        "Según el Auto 018/95 de la Corte Constitucional, omitir esa notificación viola el debido proceso, lo que "
        "llevó a declarar la nulidad de todo lo actuado con posterioridad al auto correspondiente y a devolver el "
        "expediente para subsanar el vicio.",
    ),
    (
        21,
        "¿Qué elementos debe tener la respuesta a una petición según la Corte Constitucional?",
        "Según el Auto 059/96 de la Corte Constitucional, el derecho de petición incluye no solo presentar "
        "peticiones respetuosas, sino recibir una respuesta clara, concisa y precisa sobre el asunto sometido a "
        "consideración.",
    ),
    (
        22,
        "¿Quién resuelve un conflicto de competencia territorial entre dos tribunales superiores de distrito "
        "judicial?",
        "Según el Auto 025/95 de la Corte Constitucional, la Corte Suprema de Justicia, como superior jerárquico "
        "común, es competente para decidir ese conflicto de competencias de orden territorial.",
    ),
    (
        23,
        "¿Puede la Corte Constitucional revisar un tratado internacional antes de que sea aprobado por el "
        "Congreso?",
        "Según el Auto 008/94 de la Corte Constitucional, no: la Constitución consagra el control constitucional de "
        "tratados como un paso posterior al acto aprobatorio del Congreso, y anterior a la ratificación por el "
        "Gobierno — no existe una competencia indiscriminada para revisarlos antes de su aprobación legislativa.",
    ),
    (
        24,
        "¿Quién decide sobre la suspensión de visitas de una madre a sus hijos cuando la tutela se concedió como "
        "mecanismo transitorio?",
        "Según el Auto 002/95 de la Corte Constitucional, esa decisión corresponde al ICBF, o al Juez de Familia si "
        "se inició el proceso ordinario de regulación de visitas — no es un asunto que decida directamente la Corte "
        "en sede de tutela.",
    ),
    (
        25,
        "¿Qué pretendía la demandante en el caso de la lavadora contra Alkosto?",
        "Según la Sentencia SIC 21-89363, la demandante Cecilia Orozco pretendía que se declarara que la sociedad "
        "demandada vulneró sus derechos como consumidora, y que se ordenara el reembolso del valor pagado por el "
        "electrodoméstico defectuoso.",
    ),
    (
        26,
        '¿Qué debía dejar de hacer el demandado en el caso de propiedad industrial "TODO RICO"?',
        "Según la Sentencia SIC 14-200470, se ordenó al demandado suspender definitivamente el uso de elementos "
        'nominativos y figurativos asociados al signo distintivo "TODO RICO", retirar cualquier material '
        "publicitario que los empleara, y se le prohibió usar en adelante expresiones confundibles con esos signos, "
        "de propiedad de Comestibles Ricos S.A.",
    ),
    (
        27,
        "¿A quién se aplicaba la tabla de retención en la fuente sobre dividendos del año gravable 1984?",
        "Según el Decreto 81 de 1984 (art. 6), se aplicaba a personas naturales nacionales o extranjeras residentes "
        "en el país accionistas de sociedades anónimas no abiertas, personas naturales no residentes accionistas de "
        "sociedades anónimas de cualquier tipo, y sucesiones ilíquidas de causantes nacionales o extranjeros (estos "
        "últimos si eran residentes en Colombia al morir) accionistas de sociedades anónimas.",
    ),
    (
        28,
        "¿Sigue vigente el artículo 3 del Decreto 45 de 2009 sobre el pago de declaraciones de retención por "
        "interventores?",
        "No tengo certeza de que continúe vigente: el propio fragmento indica que ese artículo fue declarado "
        "INEXEQUIBLE. El texto original establecía que el interventor debía pagar directamente las declaraciones de "
        "retención en la fuente de noviembre y diciembre de 2008 y el IVA del último bimestre de 2008 de los "
        "proveedores de las empresas intervenidas.",
    ),
    (
        29,
        "¿Qué plazo dio la DIAN a los Organismos de Acción Comunal para inscribirse en el Registro Único de "
        "Beneficiarios (RUB)?",
        "Según la Circular 1 de 2024 de la DIAN, se amplió el plazo hasta el 31 de enero de 2025 para que los "
        "Organismos de Acción Comunal que se determinen puedan inscribirse en el RUB, además de realizar mesas de "
        "trabajo con el Ministerio del Interior y campañas pedagógicas sobre el tema.",
    ),
    (
        31,
        "¿Pueden los intermediarios de valores usar los recursos de sus clientes para sus propias operaciones?",
        "Según el Concepto 2021039618-001 del 12 de abril de 2021 (Superfinanciera), no: los intermediarios de "
        "valores deben mantener separados los activos de sus clientes de los propios; esos recursos no hacen parte "
        "de los activos del intermediario ni constituyen garantía o prenda general de sus acreedores, y no pueden "
        "usarse para el cumplimiento de operaciones por cuenta propia.",
    ),
    (
        32,
        "¿Cuál es el límite de inversión en títulos participativos para los fondos de inversión colectiva "
        "cerrados según la Superfinanciera?",
        "Según el Concepto 2020311455-001 del 5 de febrero de 2021 (Superfinanciera), el límite para los FIC "
        "cerrados es del 5%, aplicable tanto a los que invierten en títulos de deuda como en participativos, para "
        "los fondos obligatorios Moderado, Mayor Riesgo y el Portafolio de Largo Plazo del fondo de Cesantía. Esta "
        "inversión es inadmisible para los fondos Conservador, Retiro Programado y el Portafolio de Corto Plazo.",
    ),
    (
        33,
        "¿Es legal en Colombia usar un broker extranjero como IQ Option sin autorización?",
        "Según el Concepto 2021041211-001 del 1 de marzo de 2021 (Superfinanciera), solo las entidades del mercado "
        "de valores del exterior autorizadas para tener oficina de representación en Colombia, o con contrato de "
        "corresponsalía con una sociedad comisionista de bolsa o corporación financiera locales, pueden publicitar "
        "sus productos en el país — las actividades del mercado de valores solo pueden ser desarrolladas por "
        "entidades autorizadas por la Superintendencia Financiera.",
    ),
    (
        34,
        "¿Cómo se elegía al Presidente de la República según el Acto Legislativo 1 de 1945?",
        "Según el Acto Legislativo 1 de 1945, el Presidente de la República era elegido en un mismo día por voto "
        "directo de los ciudadanos, para un período de cuatro años, en la forma que determinara la ley.",
    ),
    (
        35,
        "¿Podía la ley establecer categorías distintas de municipios según el Acto Legislativo 1 de 1945?",
        "Sí. Según el Acto Legislativo 1 de 1945, la ley podía establecer diversas categorías de municipios de "
        "acuerdo con su población, recursos fiscales e importancia económica, y señalar un régimen distinto de "
        "administración para cada categoría.",
    ),
    (
        36,
        "¿Qué pasaba si el Congreso no votaba la Ley de Presupuesto para el año correspondiente, según el Acto "
        "Legislativo 1 de 1945?",
        "Según el Acto Legislativo 1 de 1945, si el Congreso no votaba la Ley de Presupuesto, continuaba vigente el "
        "Presupuesto del año anterior, pero el Gobierno podía reducir gastos y suprimir o refundir empleos según lo "
        "aconsejaran los cálculos de rentas del nuevo ejercicio.",
    ),
    (
        37,
        "¿Cuánto tiempo debía esperar un Ministro para poder ser elegido al Congreso después de dejar su cargo, "
        "según el Acto Legislativo 1 de 1945?",
        "Según el Acto Legislativo 1 de 1945, el Presidente, los Ministros, los Magistrados de la Corte Suprema, los "
        "Consejeros de Estado y otros altos funcionarios no podían ser elegidos miembros del Congreso sino seis "
        "meses después de haber cesado en sus funciones.",
    ),
    (
        38,
        "¿Cuáles son las ramas del Poder Público según el Acto Legislativo 1 de 1945?",
        "Según el Acto Legislativo 1 de 1945, las ramas del Poder Público son la Legislativa, la Ejecutiva y la "
        "Jurisdiccional; el Congreso, el Gobierno y los jueces tienen funciones separadas pero colaboran "
        "armónicamente en la realización de los fines del Estado.",
    ),
    (
        39,
        "¿Qué obligación tenían los Ministros frente al Congreso según el Acto Legislativo 1 de 1945?",
        "Según el Acto Legislativo 1 de 1945, los Ministros debían presentar al Congreso, dentro de los primeros "
        "quince días de cada legislatura, un informe sobre el estado de los negocios de su Ministerio y sobre las "
        "reformas que aconsejara la experiencia; además, las Cámaras podían requerir su asistencia.",
    ),
    (
        40,
        "¿Cómo se calculaba el número de Diputados de una Asamblea Departamental según el Acto Legislativo 1 de "
        "1946?",
        "Según el Acto Legislativo 1 de 1946, las Asambleas Departamentales se componían de un Diputado por cada "
        "40.000 habitantes, más uno adicional por fracción igual o mayor a la mitad de esa cifra; si el resultado "
        "daba un número par, el Departamento tenía derecho a elegir uno más para que el total fuera siempre impar.",
    ),
]

RESPUESTA_NO_SE = "No encontré información suficiente en el índice para responder esto con certeza."

# (índice de fragmento a usar como contexto, pregunta que NO responde ese fragmento)
EJEMPLOS_NEGATIVOS = [
    (5, "¿Cuáles son los requisitos para constituir una fiducia mercantil?"),
    (30, "¿Cuál es el límite de inversión en fondos de inversión colectiva cerrados?"),
    (11, "¿Qué es la fiducia mercantil?"),
    (25, "¿Qué dice la Constitución sobre las ramas del poder público?"),
    (34, "¿Qué obligaciones tributarias impone el IVA a los responsables del régimen común?"),
    (6, "¿Qué sanciones aplica la Superintendencia de Industria y Comercio por competencia desleal?"),
    (18, "¿Cuáles son los requisitos de experiencia para el nivel asesor grado 05?"),
    (21, "¿Qué es un patrimonio autónomo en un contrato de fiducia mercantil?"),
    (32, "¿Cómo se debe notificar una tutela a un tercero con interés legítimo?"),
    (38, "¿Qué circular expidió la DIAN sobre el Registro Único de Beneficiarios en 2024?"),
]


def _construir_ejemplo(pregunta: str, resultados: list[dict], respuesta: str) -> dict:
    contexto = _formatear_fragmentos(resultados)
    prompt = (
        f"{PROMPT_SISTEMA}\n\nFragmentos disponibles:\n\n{contexto}\n\nPregunta: {pregunta}\n\nRespuesta:"
    )
    return {"prompt": prompt, "completion": " " + respuesta}


def main() -> None:
    ejemplos = []
    for indice, pregunta, respuesta in EJEMPLOS_POSITIVOS:
        resultado = _fragmento_como_resultado(MUESTRA[indice])
        ejemplos.append(_construir_ejemplo(pregunta, [resultado], respuesta))

    for indice, pregunta in EJEMPLOS_NEGATIVOS:
        resultado = _fragmento_como_resultado(MUESTRA[indice])
        ejemplos.append(_construir_ejemplo(pregunta, [resultado], RESPUESTA_NO_SE))

    salida = RAIZ / "data" / "entrenamiento.jsonl"
    with salida.open("w", encoding="utf-8") as f:
        for ej in ejemplos:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")

    print(
        f"{len(ejemplos)} ejemplos ({len(EJEMPLOS_POSITIVOS)} positivos, {len(EJEMPLOS_NEGATIVOS)} negativos) "
        f"escritos en {salida}"
    )


if __name__ == "__main__":
    main()
