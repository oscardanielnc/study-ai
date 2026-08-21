import sqlite3

from app.llm.client import LLMResult
from app.llm.costs import calcular


class TopeSuperado(Exception):
    """El gasto del mes supero el tope configurado."""


def registrar(con: sqlite3.Connection, paso: str, r: LLMResult) -> float:
    costo = calcular(r.modelo, r.tokens_in, r.tokens_out)
    con.execute(
        "INSERT INTO llm_calls (paso, modelo, tokens_in, tokens_out, costo_estimado)"
        " VALUES (?, ?, ?, ?, ?)",
        (paso, r.modelo, r.tokens_in, r.tokens_out, costo),
    )
    con.commit()
    return costo


def gasto_del_mes(con: sqlite3.Connection) -> float:
    fila = con.execute(
        "SELECT COALESCE(SUM(costo_estimado), 0) AS total FROM llm_calls"
        " WHERE strftime('%Y-%m', creado_en) = strftime('%Y-%m', 'now')"
    ).fetchone()
    return float(fila["total"])


def verificar_tope(con: sqlite3.Connection, tope: float) -> None:
    gasto = gasto_del_mes(con)
    if gasto >= tope:
        raise TopeSuperado(
            f"Gasto del mes ${gasto:.2f} alcanzo el tope ${tope:.2f}. "
            "Subelo en TOPE_GASTO_MENSUAL_USD si es intencional."
        )
