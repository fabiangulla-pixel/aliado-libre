"""Un antivirus que inspecciona TLS (Norton, Avast, Kaspersky, ESET) reemplaza
el certificado del servidor por uno suyo. Windows confía en esa raíz; `certifi`,
que es contra lo que verifica Python, no. Sin el arreglo, el usuario ve
CERTIFICATE_VERIFY_FAILED en el primer arranque y no tiene forma de entenderlo.

Estos tests protegen las dos mitades: que se aplique, y que no se "arregle"
nunca desactivando la verificación.
"""

import ssl

import confianza_tls


def test_confia_en_el_almacen_del_sistema():
    confianza_tls._ya_aplicado = False
    assert confianza_tls.confiar_en_almacen_del_sistema() is True


def test_es_idempotente():
    """Se llama desde varios puntos de entrada; llamarla dos veces no puede
    fallar ni rehacer el trabajo."""
    confianza_tls._ya_aplicado = False
    assert confianza_tls.confiar_en_almacen_del_sistema() is True
    assert confianza_tls.confiar_en_almacen_del_sistema() is True


def test_sin_truststore_no_tumba_el_arranque(monkeypatch):
    """Es una mejora de compatibilidad, no un requisito: si el paquete falta,
    el programa tiene que seguir arrancando."""
    import builtins

    real = builtins.__import__

    def sin_truststore(nombre, *args, **kwargs):
        if nombre == "truststore":
            raise ImportError("no está")
        return real(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_truststore)
    confianza_tls._ya_aplicado = False
    assert confianza_tls.confiar_en_almacen_del_sistema() is False


def test_la_verificacion_sigue_activa():
    """La mitad negativa, y la que de verdad importa.

    La receta que circula por internet para este error es desactivar la
    verificación de certificados. Este test falla si alguien la aplica: el
    contexto por defecto tiene que seguir exigiendo certificado y comprobando
    el nombre del host.
    """
    confianza_tls._ya_aplicado = False
    confianza_tls.confiar_en_almacen_del_sistema()
    ctx = ssl.create_default_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
