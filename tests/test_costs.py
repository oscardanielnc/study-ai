import pytest

from app.llm.costs import calcular


def test_calcula_costo_de_deepseek_v4_pro():
    assert calcular("deepseek/deepseek-v4-pro", 1_000_000, 1_000_000) == pytest.approx(1.305)


def test_es_proporcional_a_los_tokens():
    assert calcular("deepseek/deepseek-v4-pro", 100_000, 0) == pytest.approx(0.0435)


def test_modelo_desconocido_devuelve_cero_y_no_lanza():
    assert calcular("modelo/inexistente", 1_000_000, 1_000_000) == 0.0
