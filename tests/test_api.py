import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.db import conectar
from app.llm.fake import FakeLLMClient
from app.main import crear_app

MD = "# Ley de Ohm\n\n## Puntos clave\n\n- $V=IR$\n"
LOTE = (
    '{"preguntas": [{"enunciado": "Unidad de resistencia?",'
    ' "opciones": ["Ohmio", "Voltio", "Amperio", "Vatio"],'
    ' "correcta_idx": 0, "justificacion": "Es el ohmio."}]}'
)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), "white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    con = conectar(str(tmp_path / "t.db"))
    fake = FakeLLMClient(["Transcripcion", MD, LOTE])
    app = crear_app(con, fake, Settings())
    return TestClient(app), con, fake


def _crear_tema(c) -> int:
    r = c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()["tema_id"]


def test_crear_tema_procesa_y_devuelve_el_resumen(cliente):
    c, _, _ = cliente
    r = c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200
    tema_id = r.json()["tema_id"]

    job = c.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["estado"] == "completado", job

    tema = c.get(f"/api/temas/{tema_id}").json()
    assert tema["titulo"] == "Ley de Ohm"
    assert "$V=IR$" in tema["resumen_md"]


def test_lista_temas_incluye_el_recien_creado(cliente):
    c, _, _ = cliente
    _crear_tema(c)
    temas = c.get("/api/temas").json()
    assert len(temas) == 1 and temas[0]["n_fuentes"] == 1


def test_examen_genera_el_lote_perezosamente(cliente):
    c, _, fake = cliente
    tema_id = _crear_tema(c)

    llamadas_antes = len(fake.llamadas)
    r = c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil"})
    assert r.status_code == 200, r.text
    assert len(fake.llamadas) == llamadas_antes + 1
    assert "correcta_idx" not in r.json()["preguntas"][0]


def test_segundo_examen_no_vuelve_a_llamar_al_modelo(cliente):
    c, _, fake = cliente
    tema_id = _crear_tema(c)
    c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil"})
    llamadas = len(fake.llamadas)
    c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil"})
    assert len(fake.llamadas) == llamadas


def test_responder_y_finalizar(cliente):
    c, _, _ = cliente
    tema_id = _crear_tema(c)
    ex = c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil"}).json()

    r = c.post(
        f"/api/examenes/{ex['examen_id']}/respuestas",
        json={"pregunta_id": ex["preguntas"][0]["id"], "elegida_idx": 0},
    ).json()
    assert r["correcta"] is True and r["justificacion"] == "Es el ohmio."

    assert c.post(f"/api/examenes/{ex['examen_id']}/finalizar").json() == {
        "aciertos": 1,
        "total": 1,
    }


def test_borrar_tema(cliente):
    c, con, _ = cliente
    tema_id = _crear_tema(c)
    assert c.delete(f"/api/temas/{tema_id}").status_code == 204
    assert con.execute("SELECT COUNT(*) FROM temas").fetchone()[0] == 0


def test_historial_registra_los_examenes_terminados(cliente):
    c, _, _ = cliente
    tema_id = _crear_tema(c)
    ex = c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil"}).json()
    c.post(
        f"/api/examenes/{ex['examen_id']}/respuestas",
        json={"pregunta_id": ex["preguntas"][0]["id"], "elegida_idx": 0},
    )
    c.post(f"/api/examenes/{ex['examen_id']}/finalizar")

    hist = c.get(f"/api/temas/{tema_id}/examenes").json()
    assert len(hist) == 1
    assert hist[0]["aciertos"] == 1 and hist[0]["nivel"] == "facil"


def test_historial_omite_examenes_sin_terminar(cliente):
    c, _, _ = cliente
    tema_id = _crear_tema(c)
    c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil"})
    assert c.get(f"/api/temas/{tema_id}/examenes").json() == []


def test_gasto_expone_el_tope(cliente):
    c, _, _ = cliente
    assert c.get("/api/gasto").json()["tope_usd"] == 5.0


def test_tema_inexistente_devuelve_404(cliente):
    c, _, _ = cliente
    assert c.get("/api/temas/999").status_code == 404


def test_anadir_material_a_tema_inexistente_devuelve_404(cliente):
    c, _, _ = cliente
    r = c.post(
        "/api/temas/999/material",
        files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")},
    )
    assert r.status_code == 404
