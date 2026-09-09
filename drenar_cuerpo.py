"""Lee y tira el cuerpo pendiente de una petición antes de responder un error.

Responder un error sin leer el cuerpo deja al cliente escribiendo en un socket
que el servidor ya cerró. En Windows eso no llega como el 404 o el 400 que se
acababa de enviar: llega como `ConnectionResetError [WinError 10054]`, una
conexión abortada. El mensaje en español estaba bien escrito y el usuario nunca
lo veía.

Este módulo existe porque el mismo defecto apareció **dos veces en dos
servidores distintos**: primero en `servidor_indice/server.py` (era el fallo
intermitente de la suite) y después en `gui/server.py`, que es el que usa la
gente. Es intermitente por naturaleza —depende de si el cliente alcanzó a
escribir antes del cierre—, así que no se detecta con una sola petición y
reaparece cuando alguien añade una ruta de error nueva. Tenerlo en un sitio
único es la única forma de que arreglarlo signifique algo.
"""

from __future__ import annotations

# Por encima de esto se corta sin leer: drenar un cuerpo enorme sería trabajo
# gratis para quien manda basura. Es la única respuesta de error que el cliente
# puede no llegar a ver, y se acepta a sabiendas.
MAX_DRENAJE = 1024 * 1024
TROZO = 64 * 1024


def descartar_cuerpo(handler, max_drenaje: int = MAX_DRENAJE) -> bool:
    """Drena el cuerpo de `handler`. Devuelve True si quedó consumido.

    Marca `handler.cuerpo_consumido` para que dos caminos de error seguidos no
    intenten leer dos veces, y `handler.close_connection` cuando no se puede
    drenar: cerrar es lo correcto si el cuerpo no se va a leer.
    """
    if getattr(handler, "cuerpo_consumido", False):
        return True
    try:
        pendiente = int(handler.headers.get("Content-Length") or 0)
    except (ValueError, TypeError):
        pendiente = 0
    if pendiente <= 0:
        return True
    if pendiente > max_drenaje:
        handler.close_connection = True
        return False
    try:
        restante = pendiente
        while restante > 0:
            trozo = handler.rfile.read(min(restante, TROZO))
            if not trozo:
                break
            restante -= len(trozo)
        handler.cuerpo_consumido = True
        return True
    except OSError:
        handler.close_connection = True
        return False
