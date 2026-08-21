from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str
    modelo_transcripcion: str = "deepseek/deepseek-v4-flash-vision-exp"
    modelo_resumen: str = "deepseek/deepseek-v4-pro"
    modelo_preguntas: str = "deepseek/deepseek-v4-pro"
    db_path: str = "data/estudia.db"
    tope_gasto_mensual_usd: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
