import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import crear_router
from app.config import Settings, get_settings
from app.db import conectar
from app.llm.client import LLMClient
from app.llm.openrouter import OpenRouterClient
from app.services.ingesta import limpiar_basura, marcar_interrumpidos

ESTATICOS = Path(__file__).parent.parent / "static"


def crear_app(con: sqlite3.Connection, llm: LLMClient, settings: Settings) -> FastAPI:
    aplicacion = FastAPI(title="Estudia")

    # Todo se sirve desde el propio origen: no hay CDNs, ni analitica, ni
    # iframes. La politica puede ser cerrada de verdad, y eso convierte
    # cualquier inyeccion de HTML futura en texto inerte.
    #   - 'unsafe-inline' en style-src: KaTeX escribe estilos en linea al
    #     pintar cada formula, no hay forma de evitarlo sin nonces por peticion.
    #   - connect-src 'self': aunque alguien colara un script, no tendria a
    #     donde mandarse los datos.
    CSP = "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "form-action 'self'",
        ]
    )

    @aplicacion.middleware("http")
    async def cabeceras_de_seguridad(peticion, siguiente):
        respuesta = await siguiente(peticion)
        respuesta.headers["Content-Security-Policy"] = CSP
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "same-origin"
        respuesta.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        # El tunel de Cloudflare termina el TLS: HSTS lo pone el borde, pero
        # anunciarlo tambien desde el origen no cuesta nada.
        respuesta.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return respuesta

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
    # Despues de cerrar los jobs a medias: asi tambien se llevan los temas
    # que el reinicio dejo sin resumen.
    limpiar_basura(con)
    return crear_app(
        con,
        OpenRouterClient(settings.openrouter_api_key, base_url=settings.llm_base_url),
        settings,
    )
