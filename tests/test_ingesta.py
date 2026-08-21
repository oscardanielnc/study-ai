import io

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.config import Settings
from app.db import conectar
from app.llm.fake import FakeLLMClient
from app.services.ingesta import Archivo, crear_job, procesar

MD = "# Tema\n\n## Puntos clave\n\n- x\n"


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(buf, format="JPEG")
    return buf.getvalue()


def _pdf_en_blanco() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture
def con(tmp_path):
    con = conectar(str(tmp_path / "t.db"))
    con.execute("INSERT INTO temas (id, titulo) VALUES (1, 'Nuevo tema')")
    con.commit()
    return con


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    return Settings()


def test_guarda_una_fuente_por_archivo(con, settings):
    fake = FakeLLMClient(["T1", "T2", MD])
    job = crear_job(con, 1, 2)
    procesar(con, fake, settings, 1, job,
             [Archivo("a.jpg", _jpeg()), Archivo("b.jpg", _jpeg())])
    assert con.execute("SELECT COUNT(*) FROM fuentes").fetchone()[0] == 2


def test_marca_el_job_como_completado(con, settings):
    job = crear_job(con, 1, 1)
    procesar(con, FakeLLMClient(["T1", MD]), settings, 1, job,
             [Archivo("a.jpg", _jpeg())])
    fila = con.execute(
        "SELECT estado, progreso_actual FROM jobs WHERE id=?", (job,)
    ).fetchone()
    assert fila["estado"] == "completado"
    assert fila["progreso_actual"] == 1


def test_genera_el_resumen_al_terminar(con, settings):
    job = crear_job(con, 1, 1)
    procesar(con, FakeLLMClient(["T1", MD]), settings, 1, job,
             [Archivo("a.jpg", _jpeg())])
    assert con.execute("SELECT COUNT(*) FROM resumen").fetchone()[0] == 1


def test_un_archivo_fallido_no_pierde_los_demas(con, settings):
    # Solo 1 respuesta para 2 archivos: la 2a llamada agota el fake y lanza
    # LLMError. La fuente ya guardada debe sobrevivir.
    fake = FakeLLMClient(["T1"])
    job = crear_job(con, 1, 2)
    procesar(con, fake, settings, 1, job,
             [Archivo("a.jpg", _jpeg()), Archivo("b.jpg", _jpeg())])
    assert con.execute("SELECT COUNT(*) FROM fuentes").fetchone()[0] == 1
    assert con.execute(
        "SELECT estado FROM jobs WHERE id=?", (job,)
    ).fetchone()["estado"] == "fallido"


def test_pdf_escaneado_cae_a_vision(con, settings):
    fake = FakeLLMClient(["T-ocr", MD])
    job = crear_job(con, 1, 1)
    procesar(con, fake, settings, 1, job, [Archivo("doc.pdf", _pdf_en_blanco())])
    # Un PDF en blanco no es digital, asi que cae a vision: 1 llamada + resumen.
    assert len(fake.llamadas) == 2
    assert con.execute(
        "SELECT tipo FROM fuentes WHERE tema_id=1"
    ).fetchone()["tipo"] == "pdf"
