"""decidir() toma la abstencion con lo que trajo la busqueda, no con el orden
que le dio el enrutador de norma."""

from index.enrutador import decidir


def test_la_norma_promovida_con_menos_puntaje_no_vuelve_debil_la_busqueda():
    # el enrutador de norma sube un documento de puntaje bajo al puesto 1 (y lo
    # marca con su confianza); se decide con el mejor puntaje del conjunto
    promovida = [{"puntaje": 0.012, "confianza": "media"}, {"puntaje": 0.034}, {"puntaje": 0.020}]
    ordenada = [{"puntaje": 0.034}, {"puntaje": 0.020}, {"puntaje": 0.012}]
    assert decidir(promovida, True).motor == decidir(ordenada, True).motor != "condicional"


def test_sin_enrutador_de_norma_se_mantiene_el_comportamiento_desplegado():
    # el reordenador tampoco ordena por RRF; su abstencion no se toca sin medirla
    assert decidir([{"puntaje": 0.012}, {"puntaje": 0.034}], True).motor == "condicional"


def test_si_todo_es_debil_sigue_siendo_condicional():
    debil = [{"puntaje": 0.012, "confianza": "baja"}, {"puntaje": 0.016}]
    assert decidir(debil, True).motor == "condicional"
