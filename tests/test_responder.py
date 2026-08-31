from unittest.mock import MagicMock, patch

import pytest
import requests

from index.responder import responder


def _resultado(titulo="Decreto 1083 de 2015", fuente="gestor_normativo", texto="Texto del decreto."):
    return {
        "titulo_documento": titulo,
        "identificador_documento": titulo,
        "fuente": fuente,
        "texto": texto,
    }


def test_sin_resultados_no_llama_a_ollama():
    with patch("index.responder.requests.post") as mock_post:
        respuesta = responder("una consulta", [])
    assert "No encontré información suficiente" in respuesta
    mock_post.assert_not_called()


def test_devuelve_la_respuesta_del_modelo():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "Según el Decreto 1083 de 2015, la respuesta es X."}
    with patch("index.responder.requests.post", return_value=mock_resp) as mock_post:
        respuesta = responder("¿qué dice el decreto?", [_resultado()])
    assert respuesta == "Según el Decreto 1083 de 2015, la respuesta es X."
    args, kwargs = mock_post.call_args
    assert "Decreto 1083 de 2015" in kwargs["json"]["prompt"]
    assert "Texto del decreto." in kwargs["json"]["prompt"]


def test_lanza_runtimeerror_si_ollama_no_responde():
    with patch("index.responder.requests.post", side_effect=requests.exceptions.ConnectionError("caído")):
        with pytest.raises(RuntimeError, match="No se pudo contactar a Ollama"):
            responder("consulta", [_resultado()])


def test_lanza_runtimeerror_si_ollama_devuelve_error():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error": "model not found"}
    with patch("index.responder.requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="model not found"):
            responder("consulta", [_resultado()])


def test_usa_el_modelo_indicado():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "ok"}
    with patch("index.responder.requests.post", return_value=mock_resp) as mock_post:
        responder("consulta", [_resultado()], modelo="qwen3.6")
    assert mock_post.call_args.kwargs["json"]["model"] == "qwen3.6"
