import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import crear_router
from app.config import Settings, get_settings
from app.db import conectar
from app.llm.client import LLMClient
from app.llm.openrouter import OpenRouterClient

ESTATICOS = Path(__file__).parent.parent / "static"


def crear_app(con: sqlite3.Connection, llm: LLMClient, settings: Settings) -> FastAPI:
    aplicacion = FastAPI(title="Estudia")
    aplicacion.include_router(crear_router(con, llm, settings))
    if ESTATICOS.is_dir():
        aplicacion.mount(
            "/", StaticFiles(directory=ESTATICOS, html=True), name="static"
        )
    return aplicacion


def app() -> FastAPI:
    settings = get_settings()
    return crear_app(
        conectar(settings.db_path),
        OpenRouterClient(settings.openrouter_api_key),
        settings,
    )
