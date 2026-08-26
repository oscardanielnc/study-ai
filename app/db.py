import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"


def conectar(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrar(con)
    con.commit()
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS no anade columnas a una tabla que ya existe:
    la base de produccion necesita el ALTER a mano."""
    columnas = {f["name"] for f in con.execute("PRAGMA table_info(temas)")}
    if "usuario_id" not in columnas:
        con.execute(
            "ALTER TABLE temas ADD COLUMN usuario_id INTEGER"
            " REFERENCES usuarios(id) ON DELETE CASCADE"
        )
    if "tema_visual" not in {
        f["name"] for f in con.execute("PRAGMA table_info(usuarios)")
    }:
        con.execute(
            "ALTER TABLE usuarios ADD COLUMN tema_visual TEXT NOT NULL"
            " DEFAULT 'papel'"
        )
    if "ultimo_uso" not in {
        f["name"] for f in con.execute("PRAGMA table_info(sesiones)")
    }:
        # El DEFAULT tiene que ser constante: ALTER TABLE no acepta
        # datetime('now'). Por eso las sesiones se insertan con su fecha
        # explicita (ver auth._abrir_sesion) en vez de fiarse del default.
        con.execute(
            "ALTER TABLE sesiones ADD COLUMN ultimo_uso TEXT NOT NULL DEFAULT ''"
        )
        con.execute("UPDATE sesiones SET ultimo_uso=datetime('now')")
    # Sesiones legitimas que nacieron con '' mientras el default mandaba: son
    # de gente que entro de verdad, se les pone fecha en vez de echarla.
    con.execute("UPDATE sesiones SET ultimo_uso=datetime('now') WHERE ultimo_uso=''")
    if "usuario_id" not in {
        f["name"] for f in con.execute("PRAGMA table_info(llm_calls)")
    }:
        con.execute("ALTER TABLE llm_calls ADD COLUMN usuario_id INTEGER")
    # Despues del ALTER, nunca en schema.sql: alli se creaba antes que la
    # columna y el arranque moria con "no such column: usuario_id".
    con.execute("CREATE INDEX IF NOT EXISTS idx_temas_usuario ON temas(usuario_id)")
