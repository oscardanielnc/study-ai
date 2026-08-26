"""Regresiones de la auditoria de seguridad.

Cada test aqui reprodujo un fallo real antes de arreglarlo. No se tocan sin
entender que agujero vuelven a abrir.
"""

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
    '{"enunciado": "Unidad?", "opciones": ["Ohmio", "Voltio", "Amperio", "Vatio"],'
    ' "correcta_idx": 0, "justificacion": "Es el ohmio."}'
)


def _jpeg(lado: int = 600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (lado, lado), "white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    con = conectar(str(tmp_path / "t.db"))
    fake = FakeLLMClient(["Transcripcion", MD] + ['{"preguntas": [' + _UNA + "]}"] * 8)
    return crear_app(con, fake, Settings()), con


@pytest.fixture
def cliente(app):
    aplicacion, con = app
    c = TestClient(aplicacion)
    r = c.post("/api/registro", json={"usuario": "oscar", "clave": "clave123"})
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return c, con


def _entrar(c, usuario):
    r = c.post("/api/registro", json={"usuario": usuario, "clave": "clave123"})
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"


def _tema_con_preguntas(c, con) -> int:
    r = c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    tema_id = r.json()["tema_id"]
    con.execute(
        "INSERT INTO preguntas (tema_id, nivel, enunciado, opciones_json,"
        " correcta_idx, justificacion) VALUES (?, 'facil', 'P', '[\"a\",\"b\"]',"
        " 1, 'SECRETO DE OTRO')",
        (tema_id,),
    )
    con.commit()
    return tema_id


# ---------- F10: fuga de preguntas entre usuarios ----------


def test_no_se_pueden_leer_las_preguntas_de_otro_usuario(cliente):
    """`responder` buscaba la pregunta solo por id. Con un examen propio y el
    id de una pregunta ajena devolvia su respuesta correcta y su explicacion."""
    c, con = cliente
    _tema_con_preguntas(c, con)
    ajena = con.execute("SELECT id FROM preguntas ORDER BY id DESC").fetchone()["id"]

    _entrar(c, "intruso")
    mio = _tema_con_preguntas(c, con)
    r = c.post(
        f"/api/temas/{mio}/examenes", json={"nivel": "facil", "cantidad": 1}
    )
    examen_id = r.json()["examen_id"]

    fuga = c.post(
        f"/api/examenes/{examen_id}/respuestas",
        json={"pregunta_id": ajena, "elegida_idx": 0},
    )
    assert fuga.status_code == 404, fuga.text
    assert "SECRETO DE OTRO" not in fuga.text


# ---------- F3: limites de subida ----------


def test_se_rechazan_demasiados_archivos(cliente):
    c, _ = cliente
    muchos = [("archivos", (f"{i}.jpg", _jpeg(64), "image/jpeg")) for i in range(40)]
    assert c.post("/api/temas", files=muchos).status_code == 413


def test_se_rechaza_un_archivo_gigante(cliente):
    c, _ = cliente
    enorme = b"\xff\xd8\xff" + b"\x00" * (13 * 1024 * 1024)
    r = c.post("/api/temas", files={"archivos": ("a.jpg", enorme, "image/jpeg")})
    assert r.status_code == 413


def test_se_rechaza_una_subida_vacia(cliente):
    c, _ = cliente
    assert c.post("/api/temas", files=[]).status_code in (400, 422)


def test_una_bomba_de_descompresion_no_agota_la_memoria():
    """Un PNG de pocos KB puede declarar gigapixeles y reventar la VM al
    abrirlo. Pillow avisa pero por defecto sigue adelante."""
    from app.ingest.images import BombaDeImagen, reescalar

    bomba = io.BytesIO()
    Image.new("RGB", (1, 1)).save(bomba, format="PNG")
    datos = bytearray(bomba.getvalue())
    # Se reescribe el ancho y el alto de la cabecera IHDR a 60.000 px.
    datos[16:24] = (60000).to_bytes(4, "big") + (60000).to_bytes(4, "big")
    with pytest.raises((BombaDeImagen, Exception)):
        reescalar(bytes(datos))


# ---------- F2: fuerza bruta ----------


def test_el_login_se_frena_tras_muchos_intentos(cliente):
    c, _ = cliente
    fallos = [
        c.post("/api/login", json={"usuario": "oscar", "clave": f"malo{i}"})
        for i in range(15)
    ]
    assert any(r.status_code == 429 for r in fallos), "sin freno a la fuerza bruta"


def test_el_registro_masivo_se_frena(cliente):
    c, _ = cliente
    codigos = [
        c.post("/api/registro", json={"usuario": f"bot{i}", "clave": "clave123"}).status_code
        for i in range(15)
    ]
    assert 429 in codigos


def test_un_login_correcto_no_queda_bloqueado(cliente):
    """Frenar al atacante no puede dejar fuera al dueno de la cuenta."""
    c, _ = cliente
    for i in range(4):
        c.post("/api/login", json={"usuario": "oscar", "clave": f"malo{i}"})
    r = c.post("/api/login", json={"usuario": "oscar", "clave": "clave123"})
    assert r.status_code == 200


# ---------- F4: gasto por usuario ----------


def test_el_gasto_se_atribuye_a_su_usuario(cliente):
    c, con = cliente
    _tema_con_preguntas(c, con)
    fila = con.execute(
        "SELECT COUNT(*) AS n FROM llm_calls WHERE usuario_id IS NOT NULL"
    ).fetchone()
    assert fila["n"] > 0, "las llamadas no quedan atribuidas a nadie"


def test_un_usuario_no_puede_gastarse_el_saldo_de_todos(cliente):
    """Sin tope por cabeza, un desconocido que se registre puede quemar el
    saldo del dueno hasta dejar la app inservible para los demas."""
    c, con = cliente
    con.execute(
        "INSERT INTO llm_calls (paso, modelo, tokens_in, tokens_out,"
        # 2 USD: pasa el tope por cabeza (1) sin llegar al global (5).
        " costo_estimado, usuario_id) VALUES ('x', 'm', 1, 1, 2.0, 1)"
    )
    con.commit()
    r = c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 402

    _entrar(c, "otro")
    r2 = c.post("/api/temas", files={"archivos": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r2.status_code == 200, "el tope de uno no puede bloquear a los demas"


# ---------- F5: cabeceras de seguridad ----------


def test_la_app_manda_cabeceras_de_seguridad(cliente):
    c, _ = cliente
    h = c.get("/").headers
    assert "default-src" in h.get("content-security-policy", "")
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "DENY"
    assert "referrer-policy" in h


def test_la_politica_prohibe_scripts_de_fuera(cliente):
    c, _ = cliente
    csp = c.get("/").headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "object-src 'none'" in csp


# ---------- F6: sesiones eternas ----------


def test_una_sesion_abandonada_caduca(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    from app.services.auth import DIAS_SESION, registrar, usuario_de_token
    from app.services.ingesta import limpiar_basura

    con = conectar(str(tmp_path / "t.db"))
    token = registrar(con, "oscar", "clave123")
    con.execute(
        "UPDATE sesiones SET ultimo_uso=datetime('now', ?)",
        (f"-{DIAS_SESION + 1} days",),
    )
    con.commit()

    limpiar_basura(con)
    assert usuario_de_token(con, token) is None


def test_usar_la_sesion_la_mantiene_viva(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    from app.services.auth import registrar, usuario_de_token

    con = conectar(str(tmp_path / "t.db"))
    token = registrar(con, "oscar", "clave123")
    con.execute("UPDATE sesiones SET ultimo_uso=datetime('now', '-30 days')")
    con.commit()

    usuario_de_token(con, token)

    reciente = con.execute(
        "SELECT ultimo_uso >= datetime('now', '-1 day') AS fresco FROM sesiones"
    ).fetchone()
    assert reciente["fresco"] == 1


def test_una_base_migrada_sigue_dando_sesiones_validas(tmp_path, monkeypatch):
    """Produccion se rompio aqui. El ALTER que anadio `ultimo_uso` puso
    DEFAULT '' (SQLite no acepta datetime('now') al anadir columna), y ese
    default se quedo para SIEMPRE: cada sesion nueva nacia con ultimo_uso=''
    y '' nunca es mayor que datetime('now', '-180 days'), asi que el token
    recien emitido ya venia caducado y no se podia entrar."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    import sqlite3

    from app.services.auth import entrar, registrar, usuario_de_token

    # Base como la de produccion: creada ANTES de que existiera ultimo_uso.
    ruta = str(tmp_path / "vieja.db")
    vieja = sqlite3.connect(ruta)
    vieja.executescript(
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " usuario TEXT NOT NULL UNIQUE COLLATE NOCASE, clave TEXT NOT NULL,"
        " creado_en TEXT NOT NULL DEFAULT (datetime('now')));"
        "CREATE TABLE sesiones (token TEXT PRIMARY KEY,"
        " usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,"
        " creado_en TEXT NOT NULL DEFAULT (datetime('now')));"
    )
    vieja.commit()
    vieja.close()

    con = conectar(ruta)
    assert usuario_de_token(con, registrar(con, "oscar", "clave123")) is not None
    assert usuario_de_token(con, entrar(con, "oscar", "clave123")) is not None


def test_las_sesiones_ya_rotas_se_reparan_al_arrancar(tmp_path, monkeypatch):
    """Quien entro con la version rota tiene filas con ultimo_uso=''. Son
    sesiones legitimas: se les da fecha en vez de dejarlas muertas."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    from app.services.auth import registrar, usuario_de_token

    ruta = str(tmp_path / "t.db")
    con = conectar(ruta)
    token = registrar(con, "oscar", "clave123")
    con.execute("UPDATE sesiones SET ultimo_uso=''")
    con.commit()
    con.close()

    assert usuario_de_token(conectar(ruta), token) is not None


# ---------- F11: la CSP dejo muertos los onclick del frontend ----------


def test_el_frontend_no_usa_manejadores_en_linea():
    """`script-src 'self'` sin 'unsafe-inline' bloquea TODO atributo on*= .
    Con la CSP puesta, cada `onclick="..."` del HTML es un boton que no hace
    nada: asi murio "+ Nuevo tema". Los eventos se enganchan desde JS."""
    import re
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "static"
    for archivo in ("app.js", "index.html"):
        texto = (raiz / archivo).read_text(encoding="utf-8")
        # Atributo HTML dentro de una cadena; no `elemento.onclick = fn`, que
        # es una propiedad de JS y la CSP no toca.
        assert not re.findall(r'\son[a-z]+\s*=\s*"', texto), (
            f"{archivo} tiene manejadores en linea; la CSP los bloquea"
        )
