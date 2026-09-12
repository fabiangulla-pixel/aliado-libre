"""Proveedores externos: la clave del usuario no se guarda ni se filtra.

Todo con dobles: estos tests no llaman a ninguna API ni gastan un peso.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from index import enrutador, proveedores

CLAVE = "sk-ant-api03-EstoEsUnaClaveSecretaDeVerdad123456"


def _sdk_anthropic_falso(capturado: dict, respuesta="Según la Ley 909 de 2004..."):
    class _Mensaje:
        content = [types.SimpleNamespace(type="text", text=respuesta)]
        usage = types.SimpleNamespace(input_tokens=100, output_tokens=50)
        stop_reason = "end_turn"

    class _Mensajes:
        def create(self, **kwargs):
            capturado.update(kwargs)
            return _Mensaje()

    class _Cliente:
        def __init__(self, api_key=None):
            capturado["api_key"] = api_key
            self.messages = _Mensajes()

    return types.SimpleNamespace(Anthropic=_Cliente)


def test_usa_la_clave_que_se_le_pasa(monkeypatch):
    capturado = {}
    monkeypatch.setitem(sys.modules, "anthropic", _sdk_anthropic_falso(capturado))
    r = proveedores.generar("pregunta", "sistema", "claude", clave=CLAVE)
    assert capturado["api_key"] == CLAVE
    assert r.texto.startswith("Según la Ley 909")
    assert r.proveedor == "claude"


def test_devuelve_el_usage_para_contabilizar_costo(monkeypatch):
    capturado = {}
    monkeypatch.setitem(sys.modules, "anthropic", _sdk_anthropic_falso(capturado))
    r = proveedores.generar("pregunta", "sistema", "claude", clave=CLAVE)
    assert r.usage.input_tokens == 100


def test_encuentra_el_bloque_de_texto_aunque_no_sea_el_primero(monkeypatch):
    """Con thinking adaptativo, content[0] puede ser un bloque de razonamiento
    y no de texto: asumir content[0].text revienta con AttributeError."""

    class _Mensaje:
        content = [
            types.SimpleNamespace(type="thinking", thinking="mmm"),
            types.SimpleNamespace(type="text", text="la respuesta"),
        ]
        usage = None
        stop_reason = "end_turn"

    class _Cliente:
        def __init__(self, api_key=None):
            self.messages = types.SimpleNamespace(create=lambda **k: _Mensaje())

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Cliente))
    assert proveedores.generar("p", "s", "claude", clave=CLAVE).texto == "la respuesta"


def test_sin_bloque_de_texto_da_error_claro(monkeypatch):
    class _Mensaje:
        content = [types.SimpleNamespace(type="thinking", thinking="solo pense")]
        usage = None
        stop_reason = "max_tokens"

    class _Cliente:
        def __init__(self, api_key=None):
            self.messages = types.SimpleNamespace(create=lambda **k: _Mensaje())

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Cliente))
    with pytest.raises(proveedores.ErrorProveedor) as e:
        proveedores.generar("p", "s", "claude", clave=CLAVE)
    assert "max_tokens" in str(e.value)


def test_sin_clave_falla_con_mensaje_claro():
    with pytest.raises(proveedores.ErrorProveedor) as e:
        proveedores.generar("p", "s", "claude", clave="")
    assert "no se guarda" in str(e.value)


def test_ollama_no_pide_clave(monkeypatch):
    monkeypatch.setattr(
        proveedores, "_ollama", lambda p, s, c, m: proveedores.RespuestaProveedor("ok", None, "ollama", m)
    )
    assert proveedores.generar("p", "s", "ollama").texto == "ok"


def test_proveedor_desconocido_lista_los_validos():
    with pytest.raises(proveedores.ErrorProveedor) as e:
        proveedores.generar("p", "s", "inventado", clave=CLAVE)
    assert "claude" in str(e.value)


def test_la_clave_no_aparece_en_el_mensaje_de_error(monkeypatch):
    """Un SDK puede meter la cabecera de autorización en la excepción."""

    def _revienta(*a, **k):
        raise RuntimeError(f"401 unauthorized: x-api-key: {CLAVE}")

    monkeypatch.setattr(proveedores, "_claude", _revienta)
    with pytest.raises(proveedores.ErrorProveedor) as e:
        proveedores.generar("p", "s", "claude", clave=CLAVE)
    texto = str(e.value)
    assert CLAVE not in texto
    assert "clave omitida" in texto


def test_la_clave_no_sobrevive_a_la_llamada(monkeypatch):
    """No debe quedar en ninguna variable de módulo ni de entorno."""
    capturado = {}
    monkeypatch.setitem(sys.modules, "anthropic", _sdk_anthropic_falso(capturado))
    proveedores.generar("p", "s", "claude", clave=CLAVE)
    import os

    assert CLAVE not in "".join(os.environ.values())
    for nombre in dir(proveedores):
        valor = getattr(proveedores, nombre)
        if isinstance(valor, str):
            assert CLAVE not in valor


def test_el_modulo_no_escribe_a_disco():
    fuente = (Path(__file__).resolve().parent.parent / "index" / "proveedores.py").read_text(encoding="utf-8")
    for prohibido in ("write_text", "json.dump(", "open(ruta", "Path("):
        assert prohibido not in fuente, f"proveedores.py usa {prohibido}"
    # urlopen es legitimo (ollama local); abrir archivos, no
    assert "urlopen" in fuente


# --- enrutador --------------------------------------------------------------


def _res(*puntajes):
    return [{"id": f"f{i}", "puntaje": p} for i, p in enumerate(puntajes)]


def test_documento_claro_lo_responde_el_modelo_propio():
    d = enrutador.decidir(_res(0.09, 0.03), hay_clave_externa=True)
    assert d.motor == "local"


def test_documentos_igualados_escalan_a_ia_externa():
    d = enrutador.decidir(_res(0.041, 0.040, 0.039), hay_clave_externa=True)
    assert d.motor == "externo"


def test_sin_clave_externa_responde_igual_el_propio():
    d = enrutador.decidir(_res(0.041, 0.040), hay_clave_externa=False)
    assert d.motor == "local"
    assert "sin clave" in d.motivo.lower()


def test_sin_nada_relevante_se_abstiene():
    d = enrutador.decidir(_res(0.005), hay_clave_externa=True)
    assert d.motor == "abstenerse"
    assert not d.responde


def test_sin_resultados_se_abstiene():
    assert enrutador.decidir([], hay_clave_externa=True).motor == "abstenerse"


def test_el_mensaje_de_abstencion_distingue_no_esta_de_no_se():
    m = enrutador.mensaje_abstencion(718388)
    assert "718.388" in m
    assert "Consejo de Estado" in m and "Corte Suprema" in m
    assert "instantánea" in m


# --- costos -----------------------------------------------------------------


def test_estimar_devuelve_un_monto_y_los_tokens():
    from index import costos

    c = costos.estimar("¿Cuánto dura un encargo?" * 40, "claude-haiku-4-5")
    assert c.estimado is True
    assert c.usd > 0
    assert c.tokens_entrada > 0
    assert "estimado" in c.texto().lower()


def test_un_modelo_local_no_cuesta():
    from index import costos

    c = costos.estimar("cualquier cosa", "llama3.1")
    assert c.usd == 0
    assert "tu equipo" in c.texto()


def test_modelo_desconocido_lo_dice_en_vez_de_inventar_precio():
    from index import costos

    c = costos.estimar("hola", "modelo-que-no-existe")
    assert c.usd == 0
    assert "No conocemos el precio" in c.aviso


def test_liquidar_usa_el_consumo_real_del_proveedor():
    from index import costos

    usage = types.SimpleNamespace(input_tokens=2000, output_tokens=500)
    c = costos.liquidar(usage, "claude-haiku-4-5")
    assert c.estimado is False
    assert c.tokens_entrada == 2000
    # 2000/1e6*1 + 500/1e6*5 = 0.0045
    assert abs(c.usd - 0.0045) < 1e-9
    assert "real" in c.texto().lower()


def test_liquidar_entiende_los_nombres_de_cada_sdk():
    from index import costos

    openai_usage = types.SimpleNamespace(prompt_tokens=1000, completion_tokens=200)
    assert costos.liquidar(openai_usage, "gpt-4o-mini").tokens_entrada == 1000
    gemini_usage = types.SimpleNamespace(prompt_token_count=800, candidates_token_count=100)
    assert costos.liquidar(gemini_usage, "gemini-2.0-flash").tokens_entrada == 800


def test_sin_usage_no_inventa_un_costo():
    from index import costos

    c = costos.liquidar(None, "claude-haiku-4-5")
    assert c.usd == 0
    assert "no informó" in c.aviso


def test_los_precios_declaran_cuando_se_verificaron():
    from index import costos

    assert costos.VERIFICADO.year >= 2026
    assert set(proveedores.MODELOS_POR_DEFECTO.values()) <= set(costos.PRECIOS), (
        "hay un modelo por defecto sin precio declarado"
    )


def test_no_manda_temperature_si_el_sdk_no_la_acepta():
    """El SDK de Anthropic retiro `temperature` y eso dejo la nube caida.

    Verificado el 12-sep-2026 con anthropic 1.3.0: `messages.create` ya no
    tiene ese parametro y pasarlo levanta TypeError, asi que TODAS las
    respuestas por nube fallaban. Se comprueba contra la firma en vez de fijar
    una version, para que funcione con el SDK que el usuario tenga.
    """
    from index.proveedores import _acepta_temperatura

    def sin_temperatura(*, model, max_tokens, messages, system=None):
        pass

    def con_temperatura(*, model, max_tokens, messages, system=None, temperature=None):
        pass

    def con_kwargs(*, model, **kwargs):
        pass

    assert _acepta_temperatura(sin_temperatura) is False
    assert _acepta_temperatura(con_temperatura) is True
    # Un SDK que acepta **kwargs no se rompe al recibirla.
    assert _acepta_temperatura(con_kwargs) is True


def test_claude_no_revienta_con_un_sdk_sin_temperature(monkeypatch):
    """Prueba negativa: con el SDK real de hoy, la llamada debe armarse bien."""
    import sys
    import types

    registrado = {}

    class _Msgs:
        def create(self, *, model, max_tokens, messages, system=None):
            registrado.update(model=model, system=system)
            bloque = types.SimpleNamespace(type="text", text="ok")
            return types.SimpleNamespace(content=[bloque], usage=None, stop_reason="end_turn")

    class _Cliente:
        def __init__(self, api_key):
            self.messages = _Msgs()

    falso = types.ModuleType("anthropic")
    falso.Anthropic = _Cliente
    monkeypatch.setitem(sys.modules, "anthropic", falso)

    from index.proveedores import _claude

    r = _claude("hola", "sistema", "sk-x", "claude-haiku-4-5")
    assert r.texto == "ok"
    assert registrado["model"] == "claude-haiku-4-5"
