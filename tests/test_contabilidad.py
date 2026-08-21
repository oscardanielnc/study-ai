import pytest

from app.db import conectar
from app.llm.client import LLMResult
from app.llm.contabilidad import (
    TopeSuperado,
    gasto_del_mes,
    registrar,
    verificar_tope,
)


@pytest.fixture
def con(tmp_path):
    return conectar(str(tmp_path / "t.db"))


def _resultado(tokens_in=1_000_000, tokens_out=0):
    return LLMResult(
        texto="x",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        modelo="deepseek/deepseek-v4-pro",
    )


def test_registrar_guarda_la_llamada_y_devuelve_el_costo(con):
    costo = registrar(con, "resumen", _resultado())
    assert costo == pytest.approx(0.435)
    assert con.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] == 1


def test_gasto_del_mes_suma_las_llamadas(con):
    registrar(con, "resumen", _resultado())
    registrar(con, "preguntas", _resultado())
    assert gasto_del_mes(con) == pytest.approx(0.87)


def test_verificar_tope_lanza_cuando_se_supera(con):
    registrar(con, "resumen", _resultado(tokens_in=10_000_000))
    with pytest.raises(TopeSuperado):
        verificar_tope(con, tope=1.0)


def test_verificar_tope_no_lanza_por_debajo(con):
    registrar(con, "resumen", _resultado())
    verificar_tope(con, tope=5.0)
