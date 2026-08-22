"""Tests que SI hacen llamadas reales a OpenRouter.

Excluidos por defecto (ver pytest.ini). Ejecutar con:
    pytest -m contrato -v
"""

import io
import os

import pytest
from PIL import Image, ImageDraw

from app.config import Settings
from app.llm.openrouter import OpenRouterClient
from app.llm.prompts import TRANSCRIPCION, prompt_preguntas
from app.services.preguntas import parsear_lote

pytestmark = pytest.mark.contrato


def _imagen_con_texto() -> bytes:
    img = Image.new("RGB", (700, 200), "white")
    ImageDraw.Draw(img).text(
        (20, 80), "La resistencia se mide en ohmios", fill="black"
    )
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def cliente():
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-"):
        pytest.skip("Requiere una OPENROUTER_API_KEY real")
    s = Settings()
    return OpenRouterClient(key, base_url=s.llm_base_url), s


def test_el_modelo_de_vision_acepta_imagenes(cliente):
    llm, s = cliente
    r = llm.completar(
        modelo=s.modelo_transcripcion,
        sistema=TRANSCRIPCION,
        usuario="Transcribe esta imagen.",
        imagenes=[_imagen_con_texto()],
    )
    assert "ohmio" in r.texto.lower()
    assert r.tokens_in > 0


def test_el_modelo_de_preguntas_devuelve_json_valido(cliente):
    llm, s = cliente
    r = llm.completar(
        modelo=s.modelo_preguntas,
        sistema=prompt_preguntas("facil", 2),
        usuario="La resistencia electrica se mide en ohmios (simbolo omega).",
        max_tokens=4000,
    )
    lote = parsear_lote(r.texto)
    assert len(lote.preguntas) >= 1
    assert len(lote.preguntas[0].opciones) == 4
    assert lote.preguntas[0].justificacion.strip()
