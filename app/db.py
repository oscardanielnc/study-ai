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
    con.commit()
    return con
