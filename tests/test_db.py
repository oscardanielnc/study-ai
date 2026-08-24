import sqlite3

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


def test_una_base_vieja_se_migra_sin_perder_los_temas(tmp_path):
    """Produccion ya tenia temas sin dueno. El arranque tiene que anadir la
    columna y el indice en ese orden, no al reves."""
    ruta = str(tmp_path / "vieja.db")
    vieja = sqlite3.connect(ruta)
    vieja.executescript(
        "CREATE TABLE temas (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " titulo TEXT NOT NULL,"
        " creado_en TEXT NOT NULL DEFAULT (datetime('now')),"
        " actualizado_en TEXT NOT NULL DEFAULT (datetime('now')));"
        "INSERT INTO temas (titulo) VALUES ('De antes');"
    )
    vieja.commit()
    vieja.close()

    con = conectar(ruta)

    columnas = {f["name"] for f in con.execute("PRAGMA table_info(temas)")}
    assert "usuario_id" in columnas
    assert con.execute("SELECT titulo FROM temas").fetchone()["titulo"] == "De antes"
    con.execute("SELECT 1 FROM usuarios")  # las tablas nuevas tambien estan
