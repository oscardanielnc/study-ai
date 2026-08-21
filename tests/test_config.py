from app.config import Settings


def test_settings_lee_variables_de_entorno(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("MODELO_RESUMEN", "deepseek/deepseek-v4-pro")
    s = Settings()
    assert s.openrouter_api_key == "sk-test"
    assert s.modelo_resumen == "deepseek/deepseek-v4-pro"


def test_settings_tiene_defaults_sensatos(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    s = Settings()
    assert s.modelo_preguntas == "deepseek/deepseek-v4-pro"
    assert s.tope_gasto_mensual_usd == 5.0
    assert s.db_path.endswith("estudia.db")
