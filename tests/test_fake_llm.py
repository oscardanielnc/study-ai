import pytest

from app.llm.client import LLMError
from app.llm.fake import FakeLLMClient


def test_devuelve_las_respuestas_en_orden():
    fake = FakeLLMClient(["uno", "dos"])
    assert fake.completar(modelo="m", sistema="s", usuario="u").texto == "uno"
    assert fake.completar(modelo="m", sistema="s", usuario="u").texto == "dos"


def test_registra_las_llamadas_recibidas():
    fake = FakeLLMClient(["ok"])
    fake.completar(modelo="m", sistema="s", usuario="hola", imagenes=[b"img"])
    assert fake.llamadas[0]["usuario"] == "hola"
    assert fake.llamadas[0]["n_imagenes"] == 1


def test_lanza_llmerror_si_se_agotan_las_respuestas():
    fake = FakeLLMClient([])
    with pytest.raises(LLMError):
        fake.completar(modelo="m", sistema="s", usuario="u")


def test_reporta_tokens_para_que_el_contador_funcione():
    r = FakeLLMClient(["hola"]).completar(modelo="m", sistema="s", usuario="u")
    assert r.tokens_in > 0 and r.tokens_out > 0
