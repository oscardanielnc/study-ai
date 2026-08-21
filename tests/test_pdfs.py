import io

import pytest
from pypdf import PdfWriter

from app.ingest.pdfs import es_digital, extraer_texto


def _pdf_vacio(paginas: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_pdf_sin_texto_devuelve_cadena_vacia():
    assert extraer_texto(_pdf_vacio()).strip() == ""


def test_es_digital_true_con_texto_abundante():
    assert es_digital("x" * 500, n_paginas=2) is True


def test_es_digital_false_con_pdf_escaneado():
    assert es_digital("  \n ", n_paginas=10) is False


def test_extraer_texto_lanza_ante_datos_corruptos():
    with pytest.raises(ValueError):
        extraer_texto(b"esto no es un pdf")
