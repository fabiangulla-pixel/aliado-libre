"""Hace que Python confíe en el mismo almacén de certificados que Windows.

Por qué existe esto
-------------------
Varios antivirus de consumo (Norton, Avast, Kaspersky, ESET) interceptan el
tráfico HTTPS para inspeccionarlo: en vez del certificado de huggingface.co, el
programa recibe uno emitido al vuelo por una raíz del propio antivirus. Windows
confía en esa raíz porque el instalador la mete en el almacén del sistema, así
que el navegador no se entera de nada. Python no: verifica contra el paquete
`certifi`, que solo trae raíces públicas, y rechaza la conexión.

El resultado, sin esto, es que un usuario con antivirus abre Aliado Libre por
primera vez, la aplicación intenta descargar el modelo de embeddings, y todo lo
que ve es ``CERTIFICATE_VERIFY_FAILED`` — un error en inglés, sobre un archivo
que él no pidió, en un programa pensado para gente sin formación técnica.

Lo que NO se hace aquí
----------------------
Desactivar la verificación de certificados. Es la receta que más abunda en
internet para este error y es exactamente lo que no hay que hacer: convertiría
cada descarga del programa en una conexión sin autenticar, en nombre de
"funciona en mi máquina". Aquí se verifica igual de estrictamente, solo que
contra el almacén del sistema, que es el que ya conoce esa raíz.
"""

from __future__ import annotations

_ya_aplicado = False


def confiar_en_almacen_del_sistema() -> bool:
    """Verifica TLS contra el almacén del sistema operativo. Idempotente.

    Devuelve True si quedó aplicado. Si `truststore` no está disponible o la
    plataforma no lo soporta, devuelve False sin lanzar: es una mejora de
    compatibilidad, no un requisito para arrancar, y un fallo aquí no debe
    tumbar el programa.
    """
    global _ya_aplicado
    if _ya_aplicado:
        return True
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001 - a propósito: nunca impedir el arranque
        return False
    _ya_aplicado = True
    return True
