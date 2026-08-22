import sqlite3

from app.ingest.images import reescalar
from app.llm.client import LLMClient
from app.llm.contabilidad import registrar
from app.llm.prompts import TRANSCRIPCION


def transcribir_imagen(
    con: sqlite3.Connection,
    llm: LLMClient,
    modelo: str,
    datos: bytes,
) -> str:
    """Transcribe una imagen. El reescalado abarata el paso mas caro."""
    resultado = llm.completar(
        modelo=modelo,
        sistema=TRANSCRIPCION,
        usuario="Transcribe esta imagen.",
        imagenes=[reescalar(datos)],
        # Transcribir es copiar, no razonar. Con el razonamiento activo este
        # modelo gasta hasta el ultimo token pensando y devuelve texto vacio.
        sin_razonamiento=True,
    )
    registrar(con, "transcripcion", resultado)
    return resultado.texto.strip()
