import json

import httpx
import pytest

from app.llm.client import LLMError
from app.llm.openrouter import OpenRouterClient

RESPUESTA_OK = {
    "choices": [{"message": {"content": "hola"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 3},
}


def _cliente(handler) -> OpenRouterClient:
    transport = httpx.MockTransport(handler)
    return OpenRouterClient("sk-test", http=httpx.Client(transport=transport))


def test_parsea_una_respuesta_correcta():
    r = _cliente(lambda req: httpx.Response(200, json=RESPUESTA_OK)).completar(
        modelo="deepseek/deepseek-v4-pro", sistema="s", usuario="u"
    )
    assert (r.texto, r.tokens_in, r.tokens_out) == ("hola", 10, 3)


def test_envia_las_imagenes_como_data_url():
    capturado = {}

    def handler(req):
        capturado["body"] = req.read().decode()
        return httpx.Response(200, json=RESPUESTA_OK)

    _cliente(handler).completar(
        modelo="m", sistema="s", usuario="u", imagenes=[b"\xff\xd8\xff"]
    )
    assert "data:image/jpeg;base64," in capturado["body"]


def test_pone_la_instruccion_al_final_para_no_romper_la_cache():
    capturado = {}

    def handler(req):
        capturado["body"] = req.read().decode()
        return httpx.Response(200, json=RESPUESTA_OK)

    _cliente(handler).completar(modelo="m", sistema="SISTEMA", usuario="USUARIO")
    cuerpo = capturado["body"]
    assert cuerpo.index("SISTEMA") < cuerpo.index("USUARIO")


def test_un_429_se_convierte_en_llmerror():
    cliente = _cliente(lambda req: httpx.Response(429, json={"error": "rate limit"}))
    with pytest.raises(LLMError):
        cliente.completar(modelo="m", sistema="s", usuario="u")


def test_una_respuesta_sin_choices_se_convierte_en_llmerror():
    cliente = _cliente(lambda req: httpx.Response(200, json={}))
    with pytest.raises(LLMError):
        cliente.completar(modelo="m", sistema="s", usuario="u")


def test_por_defecto_apunta_a_openrouter():
    capturado = {}

    def handler(req):
        capturado["url"] = str(req.url)
        return httpx.Response(200, json=RESPUESTA_OK)

    _cliente(handler).completar(modelo="m", sistema="s", usuario="u")
    assert capturado["url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_acepta_otro_proveedor_compatible_con_openai():
    """DeepSeek directo evita pagar el margen de OpenRouter."""
    capturado = {}

    def handler(req):
        capturado["url"] = str(req.url)
        return httpx.Response(200, json=RESPUESTA_OK)

    cliente = OpenRouterClient(
        "sk-test",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="https://api.deepseek.com",
    )
    cliente.completar(modelo="m", sistema="s", usuario="u")
    assert capturado["url"] == "https://api.deepseek.com/chat/completions"


def test_un_content_vacio_se_convierte_en_llmerror():
    """El modelo de vision puede gastar todo el presupuesto razonando.

    Si eso se colara como transcripcion vacia, el fallo seria invisible: las
    imagenes originales ya se habrian borrado.
    """
    cliente = _cliente(
        lambda req: httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "", "reasoning_content": "mmm..."},
                     "finish_reason": "length"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8000},
            },
        )
    )
    with pytest.raises(LLMError, match="vacia"):
        cliente.completar(modelo="m", sistema="s", usuario="u")


def test_puede_pedir_que_el_modelo_no_razone():
    capturado = {}

    def handler(req):
        capturado["body"] = req.read().decode()
        return httpx.Response(200, json=RESPUESTA_OK)

    OpenRouterClient(
        "sk-test",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sin_razonamiento=True,
    ).completar(modelo="m", sistema="s", usuario="u")
    cuerpo = json.loads(capturado["body"])
    assert cuerpo["thinking"] == {"type": "disabled"}


def test_por_defecto_no_manda_el_flag_de_razonamiento():
    capturado = {}

    def handler(req):
        capturado["body"] = req.read().decode()
        return httpx.Response(200, json=RESPUESTA_OK)

    _cliente(handler).completar(modelo="m", sistema="s", usuario="u")
    assert "thinking" not in capturado["body"]
