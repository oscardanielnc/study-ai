import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

UMBRAL_CHARS_POR_PAGINA = 100


def extraer_texto(datos: bytes) -> str:
    """Extrae el texto embebido de un PDF. No usa IA."""
    try:
        lector = PdfReader(io.BytesIO(datos))
        return "\n\n".join(p.extract_text() or "" for p in lector.pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise ValueError(f"PDF ilegible: {exc}") from exc


def contar_paginas(datos: bytes) -> int:
    try:
        return len(PdfReader(io.BytesIO(datos)).pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise ValueError(f"PDF ilegible: {exc}") from exc


def es_digital(texto: str, n_paginas: int) -> bool:
    """True si el PDF trae texto real; False si es un escaneo (necesita visión)."""
    if n_paginas <= 0:
        return False
    return len(texto.strip()) / n_paginas >= UMBRAL_CHARS_POR_PAGINA


def rasterizar(datos: bytes, dpi: int = 150, max_paginas: int = 30) -> list[bytes]:
    """Convierte cada pagina de un PDF escaneado en un PNG.

    Pillow no abre PDFs, asi que sin este paso un PDF sin texto embebido no
    puede llegar al modelo de vision.
    """
    import pymupdf

    try:
        doc = pymupdf.open(stream=datos, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"PDF ilegible: {exc}") from exc
    with doc:
        return [
            doc[i].get_pixmap(dpi=dpi).tobytes("png")
            for i in range(min(len(doc), max_paginas))
        ]
