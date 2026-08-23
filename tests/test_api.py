import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.db import conectar
from app.llm.fake import FakeLLMClient
from app.main import crear_app

MD = "# Ley de Ohm\n\n## Puntos clave\n\n- $V=IR$\n"
_UNA = (
    '{"enunciado": "Unidad de resistencia?",'
    ' "opciones": ["Ohmio", "Voltio", "Amperio", "Vatio"],'
    ' "correcta_idx": 0, "justificacion": "Es el ohmio."}'
)


def _lote(n: int) -> str:
    return '{"preguntas": [' + ", ".join([_UNA] * n) + "]}"


LOTE = _lote(1)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), "white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    con = conectar(str(tmp_path / "t.db"))
    fake = FakeLLMClient(["Transcripcion", MD] + [_lote(10)] * 6)
    app = crear_app(con, fake, Settings())
    return TestClient(app), con, fake


def _crear_tema(c) -> int:
    r = c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()["tema_id"]


def _examen(c, tema_id: int, nivel: str = "facil", cantidad: int = 5) -> dict:
    """Pide un examen; si hace falta generar, espera al job y vuelve a pedirlo."""
    cuerpo = {"nivel": nivel, "cantidad": cantidad}
    r = c.post(f"/api/temas/{tema_id}/examenes", json=cuerpo).json()
    if "job_id" in r:
        assert c.get(f"/api/jobs/{r['job_id']}").json()["estado"] == "completado"
        r = c.post(f"/api/temas/{tema_id}/examenes", json=cuerpo).json()
    return r


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


def test_sin_preguntas_el_examen_devuelve_un_job_en_vez_de_bloquear(cliente):
    """Generar 40 preguntas tarda mas que el limite de 100 s del tunel."""
    c, _, _ = cliente
    tema_id = _crear_tema(c)
    r = c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 20})
    assert r.status_code == 200, r.text
    assert "job_id" in r.json() and "examen_id" not in r.json()


def test_tras_generar_el_examen_trae_exactamente_la_cantidad_pedida(cliente):
    c, _, _ = cliente
    tema_id = _crear_tema(c)
    job = c.post(
        f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 20}
    ).json()["job_id"]
    assert c.get(f"/api/jobs/{job}").json()["estado"] == "completado"

    r = c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 20})
    assert r.status_code == 200, r.text
    assert len(r.json()["preguntas"]) == 20
    assert "correcta_idx" not in r.json()["preguntas"][0]


def test_reutiliza_las_preguntas_no_vistas_antes_de_generar_mas(cliente):
    """El ahorro de tokens: no se paga dos veces por lo que ya esta en la BD."""
    c, _, fake = cliente
    tema_id = _crear_tema(c)
    c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 20})
    llamadas = len(fake.llamadas)

    r = c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 5})
    assert "examen_id" in r.json()
    assert len(fake.llamadas) == llamadas


def test_solo_genera_las_que_faltan(cliente):
    c, _, fake = cliente
    tema_id = _crear_tema(c)
    c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 10})
    c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 10})
    llamadas = len(fake.llamadas)

    # Ya hay 10 sin ver... pero se acaban de consumir. Pedir 15 genera 15.
    c.post(f"/api/temas/{tema_id}/examenes", json={"nivel": "facil", "cantidad": 15})
    assert len(fake.llamadas) == llamadas + 2  # lotes de 10 y de 5


def test_responder_y_finalizar(cliente):
    c, _, _ = cliente
    tema_id = _crear_tema(c)
    ex = _examen(c, tema_id)

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
    ex = _examen(c, tema_id)
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
    _examen(c, tema_id)
    assert c.get(f"/api/temas/{tema_id}/examenes").json() == []


def test_gasto_expone_el_tope(cliente):
    c, _, _ = cliente
    assert c.get("/api/gasto").json()["tope_usd"] == 5.0


def test_tema_inexistente_devuelve_404(cliente):
    c, _, _ = cliente
    assert c.get("/api/temas/999").status_code == 404




def test_el_job_de_un_tema_se_puede_recuperar_tras_recargar(cliente):
    # Si el movil descarta la pestana a mitad de proceso, al volver hay que
    # poder reengancharse al job sin depender de nada guardado en el cliente.
    c, _, _ = cliente
    tema_id = _crear_tema(c)
    r = c.get(f"/api/temas/{tema_id}/job")
    assert r.status_code == 200
    assert r.json()["estado"] == "completado"


def test_un_tema_sin_jobs_devuelve_null(cliente):
    c, con, _ = cliente
    con.execute("INSERT INTO temas (titulo) VALUES ('suelto')")
    con.commit()
    tema_id = con.execute("SELECT MAX(id) AS id FROM temas").fetchone()["id"]
    assert c.get(f"/api/temas/{tema_id}/job").json() is None


def test_una_subida_cortada_no_deja_temas_fantasma(cliente, monkeypatch):
    # El tema no debe existir hasta que los bytes estan en el servidor: si no,
    # una subida cortada deja una tarjeta 'Procesando...' eterna en la lista.
    c, con, _ = cliente

    async def revienta(self, size=-1):
        raise ConnectionError("cliente desconectado")

    monkeypatch.setattr("starlette.datastructures.UploadFile.read", revienta)
    with pytest.raises(ConnectionError):
        c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    assert con.execute("SELECT COUNT(*) AS n FROM temas").fetchone()["n"] == 0


def test_el_resumen_cuenta_como_un_paso_mas_del_progreso(cliente):
    # Transcribir 1 imagen y resumir son 2 pasos: si el total fuese 1, la barra
    # se quedaria clavada al 100% durante todo el resumen.
    c, _, _ = cliente
    r = c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    job = c.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["progreso_total"] == 2
    assert job["progreso_actual"] == 2
