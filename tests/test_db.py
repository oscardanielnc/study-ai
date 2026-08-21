from app.db import conectar

TABLAS = {
    "temas", "fuentes", "resumen", "preguntas",
    "examenes", "respuestas", "jobs", "llm_calls",
}


def test_conectar_crea_todas_las_tablas(tmp_path):
    con = conectar(str(tmp_path / "t.db"))
    filas = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    assert TABLAS <= {f["name"] for f in filas}


def test_conectar_activa_wal(tmp_path):
    con = conectar(str(tmp_path / "t.db"))
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_borrar_tema_borra_sus_fuentes(tmp_path):
    con = conectar(str(tmp_path / "t.db"))
    con.execute("INSERT INTO temas (id, titulo) VALUES (1, 'X')")
    con.execute(
        "INSERT INTO fuentes (tema_id, nombre_original, tipo, transcripcion)"
        " VALUES (1, 'a.jpg', 'imagen', 'texto')"
    )
    con.execute("DELETE FROM temas WHERE id = 1")
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM fuentes").fetchone()[0] == 0
