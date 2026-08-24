"""Freno a la fuerza bruta y al registro masivo.

Vive en SQLite y no en memoria a proposito: un atacante que provoque un
reinicio no puede limpiarse el contador, y con un solo worker no hay carrera
que valga la pena resolver con Redis.
"""

import sqlite3


class DemasiadosIntentos(Exception):
    """Se agoto la cuota de intentos de esta clave."""


def registrar_intento(
    con: sqlite3.Connection, clave: str, maximo: int, minutos: int
) -> None:
    """Cuenta un intento y revienta si la clave ya paso de la cuota.

    `clave` mezcla la accion y quien la hace ("login:1.2.3.4", "login:oscar"),
    de modo que frenar a un atacante por IP no bloquea a la victima por nombre
    ni al reves.
    """
    con.execute(
        "DELETE FROM intentos WHERE creado_en < datetime('now', '-1 day')"
    )
    fila = con.execute(
        "SELECT COUNT(*) AS n FROM intentos"
        " WHERE clave=? AND creado_en > datetime('now', ?)",
        (clave, f"-{minutos} minutes"),
    ).fetchone()
    if fila["n"] >= maximo:
        raise DemasiadosIntentos(
            "Demasiados intentos seguidos. Espera unos minutos y vuelve a probar."
        )
    con.execute("INSERT INTO intentos (clave) VALUES (?)", (clave,))
    con.commit()


def olvidar(con: sqlite3.Connection, clave: str) -> None:
    """Un acierto borra el historial: al dueno de la cuenta no se le castiga
    por haberse equivocado antes."""
    con.execute("DELETE FROM intentos WHERE clave=?", (clave,))
    con.commit()
