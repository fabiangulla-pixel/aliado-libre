import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._crawl_retry import crawl_con_reintentos


def test_no_pierde_progreso_ya_guardado_si_crawl_fn_falla_a_mitad_de_camino():
    """Bug real: si crawl_fn hace varios al_guardar() internos y luego falla
    (p.ej. ConnectionResetError), el archivo en disco ya tiene el progreso
    real — el wrapper no debe sobreescribirlo con una variable en memoria
    vieja. Se simula con `cargar_previos` respaldado por una lista mutable
    que representa "lo que hay en disco", actualizada por cada al_guardar()."""
    estado_en_disco = []

    def cargar_previos():
        return list(estado_en_disco)

    def checkpoint(documentos):
        estado_en_disco[:] = documentos

    def crawl_fn(al_guardar, documentos_previos, **kwargs):
        # progresa de verdad (simula 3 páginas descargadas)
        documentos = list(documentos_previos) + ["doc_nuevo_1"]
        al_guardar(documentos)
        documentos = documentos + ["doc_nuevo_2"]
        al_guardar(documentos)
        raise ConnectionError("se cortó la conexión")

    resultado = None
    try:
        with patch("scripts._crawl_retry.time.sleep"):
            resultado = crawl_con_reintentos(crawl_fn, checkpoint, cargar_previos, intentos_agotados=1)
    except ConnectionError:
        pass

    assert resultado is None  # se agotaron los intentos (solo 1) y relanzó
    # lo importante: el archivo NO quedó vacío, conserva el progreso real
    assert estado_en_disco == ["doc_nuevo_1", "doc_nuevo_2"]


def test_reintenta_desde_el_progreso_real_no_desde_una_copia_vieja():
    estado_en_disco = ["previo"]

    def cargar_previos():
        return list(estado_en_disco)

    def checkpoint(documentos):
        estado_en_disco[:] = documentos

    llamadas = []

    def crawl_fn(al_guardar, documentos_previos, **kwargs):
        llamadas.append(list(documentos_previos))
        if len(llamadas) == 1:
            al_guardar(documentos_previos + ["a"])
            raise ConnectionError("falla la primera vez")
        return documentos_previos + ["b"]

    with patch("scripts._crawl_retry.time.sleep"):
        resultado = crawl_con_reintentos(crawl_fn, checkpoint, cargar_previos, intentos_agotados=3)
    assert resultado == ["previo", "a", "b"]
    # el segundo intento debió partir de ["previo", "a"] (lo guardado en el
    # primer intento), no de ["previo"] (la copia vieja en memoria)
    assert llamadas[1] == ["previo", "a"]


def test_devuelve_resultado_de_crawl_fn_si_no_falla():
    checkpoint = MagicMock()
    resultado = crawl_con_reintentos(
        lambda al_guardar, documentos_previos, **kw: documentos_previos + ["x"],
        checkpoint,
        lambda: [],
    )
    assert resultado == ["x"]
