import json

import pytest

from app.db import conectar
from app.services.examen import finalizar, iniciar, responder, seleccionar


@pytest.fixture
def con(tmp_path):
    con = conectar(str(tmp_path / "t.db"))
    con.execute("INSERT INTO temas (id, titulo) VALUES (1, 'X')")
    for i in range(20):
        con.execute(
            "INSERT INTO preguntas (tema_id, nivel, enunciado, opciones_json,"
            " correcta_idx, justificacion, veces_vista) VALUES (1,'facil',?,?,?,?,?)",
            (f"P{i}", json.dumps(["a", "b", "c", "d"]), i % 4, f"J{i}", 0),
        )
    con.commit()
    return con


def test_selecciona_el_numero_pedido(con):
    assert len(seleccionar(con, 1, "facil", n=10)) == 10


def test_prioriza_las_menos_vistas(con):
    con.execute("UPDATE preguntas SET veces_vista=5")
    con.execute("UPDATE preguntas SET veces_vista=0 WHERE enunciado='P7'")
    con.commit()
    assert seleccionar(con, 1, "facil", n=1)[0]["enunciado"] == "P7"


def test_no_mezcla_niveles(con):
    assert seleccionar(con, 1, "dificil", n=10) == []


def test_iniciar_no_filtra_la_respuesta_correcta(con):
    _, preguntas = iniciar(con, 1, "facil", n=3)
    assert "correcta_idx" not in preguntas[0]
    assert "justificacion" not in preguntas[0]


def test_iniciar_incrementa_veces_vista(con):
    _, preguntas = iniciar(con, 1, "facil", n=3)
    ids = [p["id"] for p in preguntas]
    marcas = ",".join("?" * len(ids))
    fila = con.execute(
        f"SELECT MIN(veces_vista) v FROM preguntas WHERE id IN ({marcas})", ids
    ).fetchone()
    assert fila["v"] == 1


def test_responder_acierto_devuelve_la_justificacion(con):
    examen_id, preguntas = iniciar(con, 1, "facil", n=1)
    p = con.execute(
        "SELECT * FROM preguntas WHERE id=?", (preguntas[0]["id"],)
    ).fetchone()
    r = responder(con, examen_id, p["id"], p["correcta_idx"])
    assert r["correcta"] is True
    assert r["justificacion"] == p["justificacion"]


def test_responder_fallo_revela_la_correcta(con):
    examen_id, preguntas = iniciar(con, 1, "facil", n=1)
    p = con.execute(
        "SELECT * FROM preguntas WHERE id=?", (preguntas[0]["id"],)
    ).fetchone()
    r = responder(con, examen_id, p["id"], (p["correcta_idx"] + 1) % 4)
    assert r["correcta"] is False
    assert r["correcta_idx"] == p["correcta_idx"]


def test_finalizar_cuenta_los_aciertos(con):
    examen_id, preguntas = iniciar(con, 1, "facil", n=3)
    for i, pr in enumerate(preguntas):
        p = con.execute("SELECT * FROM preguntas WHERE id=?", (pr["id"],)).fetchone()
        elegida = p["correcta_idx"] if i == 0 else (p["correcta_idx"] + 1) % 4
        responder(con, examen_id, p["id"], elegida)
    assert finalizar(con, examen_id) == {"aciertos": 1, "total": 3}


def test_iniciar_falla_si_no_hay_preguntas_del_nivel(con):
    with pytest.raises(ValueError):
        iniciar(con, 1, "dificil", n=10)
