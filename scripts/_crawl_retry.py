"""Reintento de sesión completa compartido entre los scripts de crawl que
hacen red real (no legalize_co_github, que es lectura local). Un error de
red transitorio (ConnectionError, timeout, 502 de un backend inestable) no
debería tirar horas de progreso: se reintenta la corrida completa
reanudando desde el último checkpoint en vez de perderlo todo."""

from __future__ import annotations

import time
from collections.abc import Callable


def crawl_con_reintentos(
    crawl_fn: Callable,
    checkpoint: Callable,
    cargar_previos: Callable[[], list],
    intentos_agotados: int = 5,
    **kwargs_crawl,
) -> list:
    """`cargar_previos` relee el archivo de salida en disco, no una variable
    en memoria — bug real encontrado en producción: `crawl_fn` guarda su
    progreso incrementalmente vía `al_guardar` (`checkpoint`) según avanza,
    así que si falla a mitad de camino el archivo en disco YA tiene el
    progreso real. La versión anterior de este wrapper reintentaba con una
    variable `documentos` que solo se actualizaba cuando `crawl_fn`
    *retornaba* — si fallaba antes de retornar, esa variable seguía
    apuntando al valor de ANTES de la corrida (a menudo vacío), y el
    `checkpoint(documentos)` del `except` sobreescribía el archivo bueno con
    ese valor viejo. Pasó de verdad: perdió 1.475 documentos ya descargados
    de Superfinanciera ante un ConnectionResetError."""
    documentos = cargar_previos()
    for intento in range(1, intentos_agotados + 1):
        try:
            documentos = crawl_fn(al_guardar=checkpoint, documentos_previos=documentos, **kwargs_crawl)
            return documentos
        except Exception as e:
            documentos = cargar_previos()  # la verdad vive en el archivo, no en esta variable
            if intento == intentos_agotados:
                print(f"Se agotaron los {intentos_agotados} intentos, último error: {e}")
                raise
            espera = 30 * intento
            print(f"[intento {intento}/{intentos_agotados}] falló ({e}), reintentando en {espera}s...")
            time.sleep(espera)
    return documentos
