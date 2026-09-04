"""Pruebas de la capa conversacional. Nunca cargan el GGUF real (940 MB) ni
tocan la red: `llama_cpp.Llama` se sustituye por un doble."""

import sys
from unittest.mock import MagicMock, patch

import pytest

import index.responder as responder_mod
from index.responder import MAX_TOKENS, N_CTX, STOPS, TEMPERATURA, responder


@pytest.fixture(autouse=True)
def _sin_modelo_cacheado():
    responder_mod._modelo = None
    yield
    responder_mod._modelo = None


def _resultado(titulo="Decreto 1083 de 2015", fuente="gestor_normativo", texto="Texto del decreto."):
    return {
        "titulo_documento": titulo,
        "identificador_documento": titulo,
        "fuente": fuente,
        "texto": texto,
    }


def _falso_llama(texto="Según el Decreto 1083 de 2015, la respuesta es X."):
    llama = MagicMock(return_value={"choices": [{"text": texto}]})
    constructor = MagicMock(return_value=llama)
    modulo = MagicMock(Llama=constructor)
    return modulo, constructor, llama


@pytest.fixture
def modelo_falso(tmp_path, monkeypatch):
    gguf = tmp_path / "modelo_lora_15b.q4_k_m.gguf"
    gguf.write_bytes(b"GGUF")
    monkeypatch.setenv("ALIADO_MODELO_GGUF", str(gguf))
    modulo, constructor, llama = _falso_llama()
    monkeypatch.setitem(sys.modules, "llama_cpp", modulo)
    return gguf, constructor, llama


# --- carga perezosa ------------------------------------------------------


def test_importar_el_modulo_no_carga_el_modelo():
    assert responder_mod._modelo is None


def test_sin_resultados_no_carga_el_modelo():
    with patch.object(responder_mod, "cargar_modelo") as mock_cargar:
        respuesta = responder("una consulta", [])
    assert "No encontré información suficiente" in respuesta
    mock_cargar.assert_not_called()


def test_el_modelo_se_carga_una_sola_vez(modelo_falso):
    _, constructor, _ = modelo_falso
    responder("consulta", [_resultado()])
    responder("otra consulta", [_resultado()])
    assert constructor.call_count == 1


# --- degradación limpia --------------------------------------------------


def test_modelo_ausente_degrada_con_mensaje_util(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIADO_MODELO_GGUF", str(tmp_path / "no_existe.gguf"))
    with pytest.raises(RuntimeError) as exc:
        responder("consulta", [_resultado()])
    mensaje = str(exc.value)
    assert "modelo_lora_15b.q4_k_m.gguf" in mensaje
    assert str(tmp_path) in mensaje
    assert "ALIADO_MODELO_GGUF" in mensaje


def test_error_al_cargar_degrada(tmp_path, monkeypatch):
    gguf = tmp_path / "modelo_lora_15b.q4_k_m.gguf"
    gguf.write_bytes(b"basura")
    monkeypatch.setenv("ALIADO_MODELO_GGUF", str(gguf))
    modulo = MagicMock(Llama=MagicMock(side_effect=ValueError("archivo corrupto")))
    monkeypatch.setitem(sys.modules, "llama_cpp", modulo)
    with pytest.raises(RuntimeError, match="No se pudo cargar el modelo"):
        responder("consulta", [_resultado()])


def test_fallo_de_inferencia_degrada(modelo_falso):
    _, _, llama = modelo_falso
    llama.side_effect = ValueError("contexto excedido")
    with pytest.raises(RuntimeError, match="falló al responder"):
        responder("consulta", [_resultado()])


# --- camino feliz --------------------------------------------------------


def test_devuelve_la_respuesta_del_modelo(modelo_falso):
    _, _, llama = modelo_falso
    respuesta = responder("¿qué dice el decreto?", [_resultado()])
    assert respuesta == "Según el Decreto 1083 de 2015, la respuesta es X."
    prompt = llama.call_args.args[0]
    assert responder_mod.PROMPT_SISTEMA in prompt
    assert "Decreto 1083 de 2015" in prompt
    assert "Texto del decreto." in prompt
    assert "Pregunta: ¿qué dice el decreto?" in prompt


# --- parámetros de inferencia -------------------------------------------


def test_parametros_de_inferencia_son_los_medidos(modelo_falso):
    _, constructor, llama = modelo_falso
    responder("consulta", [_resultado()])
    assert constructor.call_args.kwargs["n_ctx"] == 8192
    kwargs = llama.call_args.kwargs
    assert kwargs["max_tokens"] == 400
    assert kwargs["temperature"] == 0.2
    assert kwargs["stop"] == ["Pregunta:", "###"]
    # y las constantes del módulo no se movieron
    assert (N_CTX, MAX_TOKENS, TEMPERATURA, STOPS) == (8192, 400, 0.2, ["Pregunta:", "###"])


# --- resolución de ruta --------------------------------------------------


def test_ruta_en_desarrollo(monkeypatch):
    monkeypatch.delenv("ALIADO_MODELO_GGUF", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    ruta = responder_mod.ruta_modelo()
    assert ruta.parent.name == "salida"
    assert ruta.parent.parent.name == "finetune"


def test_ruta_congelado(monkeypatch, tmp_path):
    monkeypatch.delenv("ALIADO_MODELO_GGUF", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "AliadoLibre.exe"))
    ruta = responder_mod.ruta_modelo()
    assert ruta == tmp_path / "modelo" / "modelo_lora_15b.q4_k_m.gguf"


def test_variable_de_entorno_acepta_carpeta(monkeypatch, tmp_path):
    monkeypatch.setenv("ALIADO_MODELO_GGUF", str(tmp_path))
    assert responder_mod.ruta_modelo() == tmp_path / "modelo_lora_15b.q4_k_m.gguf"
