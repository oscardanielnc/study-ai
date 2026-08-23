import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import crear_router
from app.config import Settings, get_settings
from app.db import conectar
from app.llm.client import LLMClient
from app.llm.openrouter import OpenRouterClient
from app.services.ingesta import marcar_interrumpidos

ESTATICOS = Path(__file__).parent.parent / "static"


def crear_app(con: sqlite3.Connection, llm: LLMClient, settings: Settings) -> FastAPI:
    aplicacion = FastAPI(title="Estudia")

    @aplicacion.middleware("http")
    async def sin_cache_en_el_armazon(peticion, siguiente):
        """Cloudflare cachea .js y .css por defecto: sin esto un despliegue
        tarda horas en llegar al movil. Lo vendido (`/vendor`, `/icons`) no
        cambia nunca y se deja cachear a gusto."""
        respuesta = await siguiente(peticion)
        ruta = peticion.url.path
        if not ruta.startswith(("/vendor/", "/icons/", "/api/")):
            respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta

    aplicacion.include_router(crear_router(con, llm, settings))
    if ESTATICOS.is_dir():
        aplicacion.mount(
            "/", StaticFiles(directory=ESTATICOS, html=True), name="static"
        )
    return aplicacion


def app() -> FastAPI:
    settings = get_settings()
    con = conectar(settings.db_path)
    marcar_interrumpidos(con)
    return crear_app(
        con,
        OpenRouterClient(settings.openrouter_api_key, base_url=settings.llm_base_url),
        settings,
    )
