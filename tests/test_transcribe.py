import io

import pytest
from PIL import Image

from app.db import conectar
from app.llm.client import LLMError
from app.llm.fake import FakeLLMClient
from app.services.transcribe import transcribir_imagen


@pytest.fixture
def con(tmp_path):
    return conectar(str(tmp_path / "t.db"))


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2000, 2000), "white").save(buf, format="JPEG")
    return buf.getvalue()


def test_devuelve_la_transcripcion(con):
    fake = FakeLLMClient(["Ley de Ohm: $V = IR$"])
    texto = transcribir_imagen(con, fake, "m", _jpeg())
    assert texto == "Ley de Ohm: $V = IR$"


def test_reescala_antes_de_enviar(con):
    fake = FakeLLMClient(["x"])
    transcribir_imagen(con, fake, "m", _jpeg())
    assert fake.llamadas[0]["n_imagenes"] == 1


def test_registra_el_gasto(con):
    transcribir_imagen(con, FakeLLMClient(["x"]), "m", _jpeg())
    assert con.execute(
        "SELECT COUNT(*) FROM llm_calls WHERE paso='transcripcion'"
    ).fetchone()[0] == 1


def test_propaga_el_error_del_llm(con):
    with pytest.raises(LLMError):
        transcribir_imagen(con, FakeLLMClient([]), "m", _jpeg())
