import json

import pytest
from pydantic import ValidationError

from app.db import conectar
from app.llm.fake import FakeLLMClient
from app.models import PreguntaGenerada
from app.services.preguntas import generar_lote, parsear_lote

UNA = {
    "enunciado": "Que mide la resistencia?",
    "opciones": ["Ohmios", "Voltios", "Amperios", "Vatios"],
    "correcta_idx": 0,
    "justificacion": "La resistencia se mide en ohmios.",
}


def _json_lote(n: int = 2) -> str:
    return json.dumps({"preguntas": [UNA] * n})


@pytest.fixture
def con(tmp_path):
    con = conectar(str(tmp_path / "t.db"))
    con.execute("INSERT INTO temas (id, titulo) VALUES (1, 'X')")
    con.execute(
        "INSERT INTO fuentes (tema_id, nombre_original, tipo, transcripcion)"
        " VALUES (1, 'a.jpg', 'imagen', 'La resistencia se mide en ohmios.')"
    )
    con.commit()
    return con


def test_rechaza_pregunta_con_tres_opciones():
    with pytest.raises(ValidationError):
        PreguntaGenerada(**{**UNA, "opciones": ["a", "b", "c"]})


def test_rechaza_indice_fuera_de_rango():
    with pytest.raises(ValidationError):
        PreguntaGenerada(**{**UNA, "correcta_idx": 4})


def test_rechaza_justificacion_vacia():
    with pytest.raises(ValidationError):
        PreguntaGenerada(**{**UNA, "justificacion": "   "})


def test_parsear_tolera_vallas_de_markdown():
    lote = parsear_lote("```json\n" + _json_lote(1) + "\n```")
    assert len(lote.preguntas) == 1


def test_generar_lote_inserta_las_preguntas(con):
    n = generar_lote(con, FakeLLMClient([_json_lote(2)]), "m", 1, "facil", n=2)
    assert n == 2
    assert con.execute(
        "SELECT COUNT(*) FROM preguntas WHERE nivel='facil'"
    ).fetchone()[0] == 2


def test_reintenta_una_vez_ante_json_invalido(con):
    fake = FakeLLMClient(["esto no es json", _json_lote(1)])
    assert generar_lote(con, fake, "m", 1, "facil", n=1) == 1
    assert len(fake.llamadas) == 2


def test_falla_si_el_reintento_tambien_es_invalido(con):
    fake = FakeLLMClient(["nada", "tampoco"])
    with pytest.raises(ValueError):
        generar_lote(con, fake, "m", 1, "facil", n=1)
