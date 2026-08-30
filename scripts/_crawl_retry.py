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
    documentos_previos: list,
    intentos_agotados: int = 5,
    **kwargs_crawl,
) -> list:
    documentos = documentos_previos
    for intento in range(1, intentos_agotados + 1):
        try:
            documentos = crawl_fn(al_guardar=checkpoint, documentos_previos=documentos, **kwargs_crawl)
            return documentos
        except Exception as e:
            checkpoint(documentos)
            if intento == intentos_agotados:
                print(f"Se agotaron los {intentos_agotados} intentos, último error: {e}")
                raise
            espera = 30 * intento
            print(f"[intento {intento}/{intentos_agotados}] falló ({e}), reintentando en {espera}s...")
            time.sleep(espera)
    return documentos
