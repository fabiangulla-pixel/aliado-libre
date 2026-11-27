"""Plazos en días hábiles con los festivos de Colombia.

«¿Hasta cuándo tienen para contestarme?» es la pregunta que sigue a radicar un
derecho de petición o un reclamo. La respuesta es aritmética, pero con trampa:
los festivos colombianos se mueven.

Festivos (Ley 51 de 1983 y fiestas religiosas que siguen la Pascua):

- Fijos: 1 ene, 1 may, 20 jul, 7 ago, 8 dic, 25 dic.
- Trasladables al lunes siguiente si no caen en lunes («Ley Emiliani»): 6 ene,
  19 mar, 29 jun, 15 ago, 12 oct, 1 nov, 11 nov.
- Según la Pascua: Jueves y Viernes Santo (no se trasladan); Ascensión (+43
  días, lunes), Corpus Christi (+64, lunes) y Sagrado Corazón (+71, lunes).

Conteo (regla general de los términos en días hábiles): el día en que se
radica NO cuenta; el término empieza el siguiente día hábil y vence al final
del último. Sábados, domingos y festivos no cuentan. No se modelan vacancias
judiciales ni cierres propios de cada entidad: la página lo advierte.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
DIAS = "lunes martes miércoles jueves viernes sábado domingo".split()
MAX_DIAS = 400

FIJOS = {(1, 1): "Año Nuevo", (5, 1): "Día del Trabajo", (7, 20): "Día de la Independencia",
         (8, 7): "Batalla de Boyacá", (12, 8): "Inmaculada Concepción", (12, 25): "Navidad"}  # fmt: skip
TRASLADABLES = {(1, 6): "Reyes Magos", (3, 19): "San José", (6, 29): "San Pedro y San Pablo",
                (8, 15): "Asunción de la Virgen", (10, 12): "Día de la Raza", (11, 1): "Todos los Santos",
                (11, 11): "Independencia de Cartagena"}  # fmt: skip


def pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo de Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = (h + l_ - 7 * m + 114) % 31 + 1
    return date(anio, mes, dia)


def _lunes_siguiente(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=64)
def festivos(anio: int) -> dict[date, str]:
    salida: dict[date, str] = {}

    def poner(d: date, nombre: str) -> None:
        # Dos festivos pueden caer el mismo lunes (2025: San Pedro y Sagrado Corazón, 30 de junio).
        salida[d] = f"{salida[d]} y {nombre}" if d in salida else nombre

    for (m, d), n in FIJOS.items():
        poner(date(anio, m, d), n)
    for (m, d), n in TRASLADABLES.items():
        poner(_lunes_siguiente(date(anio, m, d)), n)
    p = pascua(anio)
    poner(p - timedelta(days=3), "Jueves Santo")
    poner(p - timedelta(days=2), "Viernes Santo")
    poner(p + timedelta(days=43), "Ascensión del Señor")
    poner(p + timedelta(days=64), "Corpus Christi")
    poner(p + timedelta(days=71), "Sagrado Corazón")
    return dict(sorted(salida.items()))


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in festivos(d.year)


def fecha_larga(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def vencimiento(desde: date, dias_habiles: int) -> dict:
    """Último día del término de `dias_habiles` contados desde el día hábil
    siguiente a `desde`. Lanza ValueError con un mensaje legible."""
    if not 1 <= dias_habiles <= MAX_DIAS:
        raise ValueError(f"El número de días hábiles debe estar entre 1 y {MAX_DIAS}.")
    d = desde
    contados = 0
    saltados: list[dict] = []
    while contados < dias_habiles:
        d += timedelta(days=1)
        if es_habil(d):
            contados += 1
        elif d.weekday() < 5:
            saltados.append({"fecha": d.isoformat(), "festivo": festivos(d.year)[d]})
    return {
        "desde": desde.isoformat(),
        "dias_habiles": dias_habiles,
        "vence": d.isoformat(),
        "vence_texto": fecha_larga(d),
        "dias_calendario": (d - desde).days,
        "festivos_saltados": saltados,
        "aviso": (
            "Cálculo orientativo: el día de radicación no cuenta y se excluyen sábados, domingos y festivos "
            "nacionales. No incluye vacancias judiciales ni días sin atención propios de cada entidad."
        ),
    }
