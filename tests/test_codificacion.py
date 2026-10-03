"""Reparación de doble codificación UTF-8: arregla el mojibake y no toca el texto sano."""

import pytest

from ingest.codificacion import reparar, tiene_mojibake


@pytest.mark.parametrize(
    "danado, sano",
    [
        ("ARTÃ\x8dCULO 1058. DECLARACIÃ\x93N DEL ESTADO", "ARTÍCULO 1058. DECLARACIÓN DEL ESTADO"),
        (
            "de cÃ¡ncer durante cuatro (4) aÃ±os sin recaÃ\xaddas",
            "de cáncer durante cuatro (4) años sin recaídas",
        ),
    ],
)
def test_repara_mojibake(danado, sano):
    assert tiene_mojibake(danado)
    assert reparar(danado) == sano


@pytest.mark.parametrize(
    "texto",
    [
        "texto normal con tildes: canción, año, Ñandú",
        "ARTÍCULO 5o. Él dijo «hola» — y siguió",
        "Ángel Ávila presentó la demanda",  # Á mayúscula legítima, no mojibake
        "",
    ],
)
def test_texto_sano_sale_identico(texto):
    assert not tiene_mojibake(texto)
    assert reparar(texto) is texto
