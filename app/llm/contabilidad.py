import sqlite3

from app.llm.client import LLMResult
from app.llm.costs import calcular


class TopeSuperado(Exception):
    """El gasto del mes supero el tope configurado."""


def dueno_del_tema(con: sqlite3.Connection, tema_id: int) -> int | None:
    fila = con.execute(
        "SELECT usuario_id FROM temas WHERE id=?", (tema_id,)
    ).fetchone()
    return None if fila is None else fila["usuario_id"]


def registrar(
    con: sqlite3.Connection,
    paso: str,
    r: LLMResult,
    usuario_id: int | None = None,
) -> float:
    """Cada llamada queda atribuida a quien la provoco. Sin eso, el tope solo
    puede ser global y un desconocido que se registre puede quemar el saldo de
    todos."""
    costo = calcular(r.modelo, r.tokens_in, r.tokens_out)
    con.execute(
        "INSERT INTO llm_calls (paso, modelo, tokens_in, tokens_out,"
        " costo_estimado, usuario_id) VALUES (?, ?, ?, ?, ?, ?)",
        (paso, r.modelo, r.tokens_in, r.tokens_out, costo, usuario_id),
    )
    con.commit()
    return costo


def gasto_del_mes(con: sqlite3.Connection, usuario_id: int | None = None) -> float:
    donde = " AND usuario_id=?" if usuario_id is not None else ""
    fila = con.execute(
        "SELECT COALESCE(SUM(costo_estimado), 0) AS total FROM llm_calls"
        " WHERE strftime('%Y-%m', creado_en) = strftime('%Y-%m', 'now')" + donde,
        (usuario_id,) if usuario_id is not None else (),
    ).fetchone()
    return float(fila["total"])


def verificar_tope(
    con: sqlite3.Connection,
    tope: float,
    usuario_id: int | None = None,
    tope_usuario: float | None = None,
) -> None:
    """Dos vallas: la de la factura entera y la de cada cabeza. Sin la segunda,
    el primero que llegue puede dejar la app inservible para los demas."""
    gasto = gasto_del_mes(con)
    if gasto >= tope:
        raise TopeSuperado(
            f"Gasto del mes ${gasto:.2f} alcanzo el tope ${tope:.2f}. "
            "Subelo en TOPE_GASTO_MENSUAL_USD si es intencional."
        )
    if usuario_id is not None and tope_usuario is not None:
        mio = gasto_del_mes(con, usuario_id)
        if mio >= tope_usuario:
            raise TopeSuperado(
                f"Has usado ${mio:.2f} este mes, el maximo por usuario es "
                f"${tope_usuario:.2f}. Vuelve el mes que viene."
            )
