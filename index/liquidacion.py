"""Liquidación laboral orientativa: cesantías, intereses, prima, vacaciones e
indemnización por despido sin justa causa.

Existe por el hueco más claro de la app: «me deben la liquidación» (0 de 26
consultas reales cubiertas, 12-sep-2026). La pregunta casi nunca es «¿qué
norma?» sino «¿cuánto?».

**APAGADA POR DEFECTO** (`ALIADO_LIQUIDACION=1` la enciende) hasta que una
abogada revise las fórmulas: un cálculo de dinero mal hecho hace más daño que
no tener calculadora. Cada línea devuelve su fórmula y su fuente para que esa
revisión sea rápida.

Fórmulas (Código Sustantivo del Trabajo, verificado el 27-nov-2026 que la Ley
2466 de 2025 no modificó los arts. 64, 186/189, 249 ni 306: modifica 46, 47,
59 y otros, y adiciona parágrafos al art. 99 de la Ley 50 de 1990):

- Días por calendario comercial de 360 (cada mes cuenta 30), inclusivo.
- Cesantías (art. 249): (salario + auxilio de transporte) × días / 360, desde
  el 1 de enero del año del retiro (las de años anteriores se consignan al
  fondo antes del 15 de febrero) o desde el ingreso si fue después.
- Intereses a las cesantías (Ley 52 de 1975): cesantías × días × 12 % / 360.
- Prima de servicios (art. 306): (salario + auxilio) × días del semestre / 360.
- Vacaciones (arts. 186 y 189): salario × días trabajados / 720, menos los días
  ya disfrutados (salario / 30 por día). El auxilio de transporte no cuenta.
- Indemnización (art. 64, modificado por el art. 28 de la Ley 789 de 2002):
  indefinido con salario < 10 SMMLV: 30 días por el primer año y 20 por cada
  año siguiente, proporcional; ≥ 10 SMMLV: 20 y 15. Término fijo: salarios del
  tiempo que faltaba. Obra o labor: el tiempo que faltaba, mínimo 15 días.

El salario mínimo y el auxilio de transporte NO van fijos en el código: los
escribe la persona (salen en su desprendible). No pudimos confirmar en fuente
primaria las cifras de 2026, y una cifra horneada caduca cada enero.
"""

from __future__ import annotations

import calendar
import os
from datetime import date

FUENTES = {
    "cesantias": "Código Sustantivo del Trabajo, art. 249",
    "intereses": "Ley 52 de 1975, art. 1",
    "prima": "Código Sustantivo del Trabajo, art. 306",
    "vacaciones": "Código Sustantivo del Trabajo, arts. 186 y 189",
    "indemnizacion": "Código Sustantivo del Trabajo, art. 64 (modificado por la Ley 789 de 2002, art. 28)",
}
TIPOS_CONTRATO = ("indefinido", "fijo", "obra")
MOTIVOS = ("despido_sin_justa_causa", "renuncia", "justa_causa", "mutuo_acuerdo", "fin_del_plazo")
LEY_789 = date(2002, 12, 27)  # vigencia de la Ley 789 de 2002


class ErrorLiquidacion(ValueError):
    pass


def activa() -> bool:
    return os.environ.get("ALIADO_LIQUIDACION", "").strip() == "1"


def dias360(desde: date, hasta: date) -> int:
    """Días entre dos fechas, ambas incluidas, con meses de 30 días."""
    if hasta < desde:
        return 0
    d1 = min(desde.day, 30)
    d2 = 30 if hasta.day == calendar.monthrange(hasta.year, hasta.month)[1] else min(hasta.day, 30)
    return (hasta.year - desde.year) * 360 + (hasta.month - desde.month) * 30 + (d2 - d1) + 1


def _pesos(x: float) -> int:
    return round(x)


def _fecha(valor, nombre: str) -> date:
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError):
        raise ErrorLiquidacion(f"Falta o no es válida la fecha de {nombre} (AAAA-MM-DD).") from None


def _entero(valor, nombre: str, minimo: int = 0) -> int:
    try:
        n = int(float(str(valor).replace(".", "").replace(",", ".")) if isinstance(valor, str) else valor)
    except (TypeError, ValueError):
        raise ErrorLiquidacion(f"El valor de {nombre} no es un número.") from None
    if n < minimo:
        raise ErrorLiquidacion(f"El valor de {nombre} no puede ser menor que {minimo}.")
    return n


def calcular(datos: dict) -> dict:
    ingreso = _fecha(datos.get("fecha_ingreso"), "ingreso")
    retiro = _fecha(datos.get("fecha_retiro"), "retiro")
    if retiro < ingreso:
        raise ErrorLiquidacion("La fecha de retiro es anterior a la de ingreso.")
    salario = _entero(datos.get("salario"), "salario", 1)
    auxilio = _entero(datos.get("auxilio_transporte") or 0, "auxilio de transporte")
    disfrutadas = _entero(datos.get("vacaciones_disfrutadas") or 0, "días de vacaciones disfrutados")
    tipo = datos.get("tipo_contrato") or "indefinido"
    motivo = datos.get("motivo") or "renuncia"
    if tipo not in TIPOS_CONTRATO or motivo not in MOTIVOS:
        raise ErrorLiquidacion("Tipo de contrato o motivo de terminación no reconocido.")
    alto = bool(datos.get("salario_mayor_10_smmlv"))

    avisos: list[str] = [
        "CÁLCULO ORIENTATIVO, en revisión jurídica. No reemplaza la liquidación del empleador ni la asesoría "
        "de un abogado, un consultorio jurídico o el inspector de trabajo.",
    ]
    lineas: list[dict] = []
    base_prest = salario + auxilio

    # Cesantías e intereses: periodo del año del retiro.
    inicio_ces = max(ingreso, date(retiro.year, 1, 1))
    dias_ces = dias360(inicio_ces, retiro)
    ces = base_prest * dias_ces / 360
    lineas.append(
        {
            "concepto": "Cesantías",
            "valor": _pesos(ces),
            "fuente": FUENTES["cesantias"],
            "formula": f"({salario:,} + {auxilio:,}) × {dias_ces} días / 360".replace(",", "."),
            "periodo": f"{inicio_ces.isoformat()} a {retiro.isoformat()}",
        }
    )
    intereses = ces * dias_ces * 0.12 / 360
    lineas.append(
        {
            "concepto": "Intereses a las cesantías",
            "valor": _pesos(intereses),
            "fuente": FUENTES["intereses"],
            "formula": f"{_pesos(ces):,} × {dias_ces} × 12 % / 360".replace(",", "."),
            "periodo": f"{inicio_ces.isoformat()} a {retiro.isoformat()}",
        }
    )
    if inicio_ces > ingreso:
        avisos.append(
            "Las cesantías de años anteriores debían consignarse en tu fondo de cesantías: no se suman aquí. "
            "Si no te las consignaron, eso se reclama aparte (puede haber sanción por no consignación)."
        )

    # Prima: semestre en curso.
    inicio_sem = date(retiro.year, 1 if retiro.month <= 6 else 7, 1)
    inicio_prima = max(ingreso, inicio_sem)
    dias_prima = dias360(inicio_prima, retiro)
    lineas.append(
        {
            "concepto": "Prima de servicios",
            "valor": _pesos(base_prest * dias_prima / 360),
            "fuente": FUENTES["prima"],
            "formula": f"({salario:,} + {auxilio:,}) × {dias_prima} días / 360".replace(",", "."),
            "periodo": f"{inicio_prima.isoformat()} a {retiro.isoformat()}",
        }
    )

    # Vacaciones: todo el tiempo trabajado, menos lo disfrutado.
    dias_total = dias360(ingreso, retiro)
    vac_dias = dias_total * 15 / 360 - disfrutadas
    lineas.append(
        {
            "concepto": "Vacaciones no disfrutadas",
            "valor": _pesos(max(0.0, vac_dias) * salario / 30),
            "fuente": FUENTES["vacaciones"],
            "formula": (
                f"({dias_total} días × 15 / 360 − {disfrutadas} disfrutados) × {salario:,} / 30".replace(
                    ",", "."
                )
            ),
            "periodo": f"{ingreso.isoformat()} a {retiro.isoformat()}",
        }
    )
    if vac_dias < 0:
        avisos.append("Según los datos, disfrutaste más vacaciones de las causadas: no hay saldo a favor.")

    # Indemnización.
    if motivo == "despido_sin_justa_causa":
        diario = salario / 30
        if tipo == "indefinido":
            años = dias_total / 360
            primero, siguientes = (20, 15) if alto else (30, 20)
            dias_ind = primero + max(0.0, años - 1) * siguientes
            formula = (
                f"{primero} días por el primer año + {siguientes} por cada año adicional "
                f"({años:.2f} años en total) = {dias_ind:.1f} días × {salario:,} / 30"
            ).replace(",", ".")
            # Parágrafo transitorio del art. 28 de la Ley 789: quien el 27-dic-2002
            # ya tenía 10 años o más de servicio conserva la tabla anterior.
            if dias360(ingreso, LEY_789) >= 3600:
                avisos.append(
                    "El 27 de diciembre de 2002 ya llevabas 10 años o más en este empleo: te aplica un "
                    "régimen de "
                    "transición (Ley 789 de 2002, art. 28) que esta calculadora no cubre. El valor de la "
                    "indemnización de abajo puede ser menor que el que te corresponde."
                )
        else:
            faltaban = _entero(datos.get("dias_faltantes") or 0, "días que faltaban")
            dias_ind = max(faltaban, 15) if tipo == "obra" else faltaban
            formula = (
                f"{dias_ind} días que faltaban"
                + (" (mínimo 15 en obra o labor)" if tipo == "obra" else "")
                + f" × {salario:,} / 30".replace(",", ".")
            )
            if not faltaban:
                avisos.append("Escribe cuántos días faltaban para terminar el contrato o la obra.")
        lineas.append(
            {
                "concepto": "Indemnización por despido sin justa causa",
                "valor": _pesos(dias_ind * diario),
                "fuente": FUENTES["indemnizacion"],
                "formula": formula,
                "periodo": "",
            }
        )
    else:
        avisos.append(
            "Con el motivo elegido no hay indemnización por despido sin justa causa. Si crees que el "
            "despido no "
            "tuvo justa causa, eso lo decide un juez o se concilia."
        )

    if auxilio == 0 and salario > 0:
        avisos.append(
            "Pusiste auxilio de transporte en cero. Si ganabas hasta dos salarios mínimos, tenías "
            "derecho a él y "
            "se suma para cesantías y prima: míralo en tu desprendible."
        )
    avisos.append(
        "Si al terminar el contrato no te pagaron, la ley prevé una indemnización por mora (CST, art. "
        "65) que esta "
        "calculadora no estima."
    )
    return {
        "lineas": lineas,
        "total": sum(x["valor"] for x in lineas),
        "dias_trabajados": dias_total,
        "avisos": avisos,
    }
