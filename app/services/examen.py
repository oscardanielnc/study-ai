import json
import sqlite3

from app.models import Nivel


def seleccionar(
    con: sqlite3.Connection, tema_id: int, nivel: Nivel, n: int = 10
) -> list[sqlite3.Row]:
    """Las menos vistas primero; el azar desempata para variar entre examenes."""
    return con.execute(
        "SELECT * FROM preguntas WHERE tema_id=? AND nivel=?"
        " ORDER BY veces_vista ASC, RANDOM() LIMIT ?",
        (tema_id, nivel, n),
    ).fetchall()


def iniciar(
    con: sqlite3.Connection, tema_id: int, nivel: Nivel, n: int = 10
) -> tuple[int, list[dict]]:
    filas = seleccionar(con, tema_id, nivel, n)
    if not filas:
        raise ValueError(f"No hay preguntas de nivel {nivel} para el tema {tema_id}")

    cur = con.execute(
        "INSERT INTO examenes (tema_id, nivel) VALUES (?, ?)", (tema_id, nivel)
    )
    examen_id = int(cur.lastrowid)
    con.executemany(
        "UPDATE preguntas SET veces_vista = veces_vista + 1 WHERE id=?",
        [(f["id"],) for f in filas],
    )
    con.commit()

    # Nunca enviamos correcta_idx ni justificacion al cliente antes de responder.
    publicas = [
        {
            "id": f["id"],
            "enunciado": f["enunciado"],
            "opciones": json.loads(f["opciones_json"]),
        }
        for f in filas
    ]
    return examen_id, publicas


def responder(
    con: sqlite3.Connection, examen_id: int, pregunta_id: int, elegida_idx: int
) -> dict:
    p = con.execute("SELECT * FROM preguntas WHERE id=?", (pregunta_id,)).fetchone()
    if p is None:
        raise ValueError(f"Pregunta {pregunta_id} inexistente")

    correcta = elegida_idx == p["correcta_idx"]
    con.execute(
        "INSERT INTO respuestas (examen_id, pregunta_id, elegida_idx, correcta)"
        " VALUES (?, ?, ?, ?)",
        (examen_id, pregunta_id, elegida_idx, int(correcta)),
    )
    con.commit()
    return {
        "correcta": correcta,
        "correcta_idx": p["correcta_idx"],
        "justificacion": p["justificacion"],
    }


def finalizar(con: sqlite3.Connection, examen_id: int) -> dict:
    fila = con.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(correcta), 0) AS aciertos"
        " FROM respuestas WHERE examen_id=?",
        (examen_id,),
    ).fetchone()
    aciertos, total = int(fila["aciertos"]), int(fila["total"])
    con.execute(
        "UPDATE examenes SET terminado_en=datetime('now'), aciertos=?, total=?"
        " WHERE id=?",
        (aciertos, total, examen_id),
    )
    con.commit()
    return {"aciertos": aciertos, "total": total}
