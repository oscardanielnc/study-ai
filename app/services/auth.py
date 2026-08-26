"""Usuarios y sesiones.

Sin correo, sin recuperacion, sin perfiles: usuario y contrasena. Lo minimo
para que cada uno vea sus propios temas y no gaste el saldo de los demas por
accidente.
"""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3

# scrypt viene en la stdlib: no hay que compilar bcrypt en el ARM de la VM.
# Con estos parametros tarda ~100 ms, que es caro para quien prueba miles de
# contrasenas y ni se nota al entrar.
_COSTE, _BLOQUE, _PARALELO = 2**14, 8, 1
_ALGORITMO = "scrypt"

# Seis meses sin abrir la app y la sesion se cierra sola. Nunca caducar
# convierte un token robado en acceso perpetuo; seis meses no molesta a
# quien la usa, porque cada uso la renueva.
DIAS_SESION = 180

USUARIO_VALIDO = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
CLAVE_MINIMA = 6


class DatosInvalidos(Exception):
    """El usuario o la clave no cumplen las reglas."""


class UsuarioOcupado(Exception):
    """Ya existe alguien con ese nombre."""


class CredencialesMalas(Exception):
    """Usuario o clave incorrectos."""


def _derivar(clave: str, sal: bytes) -> str:
    return hashlib.scrypt(
        clave.encode("utf-8"),
        salt=sal,
        n=_COSTE,
        r=_BLOQUE,
        p=_PARALELO,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    ).hex()


def cifrar(clave: str) -> str:
    sal = os.urandom(16)
    return f"{_ALGORITMO}${sal.hex()}${_derivar(clave, sal)}"


def comprobar(clave: str, guardado: str) -> bool:
    try:
        algoritmo, sal, esperado = guardado.split("$")
    except ValueError:
        return False
    if algoritmo != _ALGORITMO:
        return False
    # compare_digest y no ==: comparar hashes byte a byte filtra por el tiempo
    # cuantos coinciden.
    return hmac.compare_digest(_derivar(clave, bytes.fromhex(sal)), esperado)


def _validar(usuario: str, clave: str) -> None:
    if not USUARIO_VALIDO.match(usuario or ""):
        raise DatosInvalidos(
            "El usuario necesita entre 3 y 32 caracteres, sin espacios"
            " (letras, numeros, punto, guion o guion bajo)."
        )
    if len(clave or "") < CLAVE_MINIMA:
        raise DatosInvalidos(
            f"La contrasena necesita al menos {CLAVE_MINIMA} caracteres."
        )


def _abrir_sesion(con: sqlite3.Connection, usuario_id: int) -> str:
    """Un token opaco por sesion. No caduca: volver a pedir la contrasena cada
    poco en el movil es justo lo que hace que la gente deje de usar la app.
    Se puede revocar borrando la fila."""
    token = secrets.token_urlsafe(32)
    # `ultimo_uso` se escribe aqui y no se deja al DEFAULT de la columna: en la
    # base de produccion ese default es '' (el ALTER que la anadio no podia
    # usar datetime('now')), y una sesion con '' nace ya caducada.
    con.execute(
        "INSERT INTO sesiones (token, usuario_id, ultimo_uso)"
        " VALUES (?, ?, datetime('now'))",
        (token, usuario_id),
    )
    con.commit()
    return token


def registrar(con: sqlite3.Connection, usuario: str, clave: str) -> str:
    _validar(usuario, clave)
    try:
        cur = con.execute(
            "INSERT INTO usuarios (usuario, clave) VALUES (?, ?)",
            (usuario, cifrar(clave)),
        )
    except sqlite3.IntegrityError as exc:
        raise UsuarioOcupado("Ese usuario ya existe.") from exc
    con.commit()
    return _abrir_sesion(con, int(cur.lastrowid))


def entrar(con: sqlite3.Connection, usuario: str, clave: str) -> str:
    fila = con.execute(
        "SELECT id, clave FROM usuarios WHERE usuario=?", (usuario,)
    ).fetchone()
    # Se comprueba igual aunque no exista, para que el tiempo de respuesta no
    # diga si el usuario esta registrado.
    guardado = fila["clave"] if fila else cifrar("_")
    if not comprobar(clave, guardado) or fila is None:
        raise CredencialesMalas("Usuario o contrasena incorrectos.")
    return _abrir_sesion(con, int(fila["id"]))


def salir(con: sqlite3.Connection, token: str) -> None:
    con.execute("DELETE FROM sesiones WHERE token=?", (token,))
    con.commit()


def usuario_de_token(con: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    if not token:
        return None
    fila = con.execute(
        "SELECT u.id, u.usuario, u.tema_visual FROM sesiones s"
        " JOIN usuarios u ON u.id=s.usuario_id"
        " WHERE s.token=? AND s.ultimo_uso > datetime('now', ?)",
        (token, f"-{DIAS_SESION} days"),
    ).fetchone()
    if fila is None:
        return None
    # Se refresca como mucho una vez al dia: marcar cada peticion seria una
    # escritura por lectura sin ganar nada.
    con.execute(
        "UPDATE sesiones SET ultimo_uso=datetime('now')"
        " WHERE token=? AND ultimo_uso < datetime('now', '-1 day')",
        (token,),
    )
    con.commit()
    return fila


def limpiar_sesiones(con: sqlite3.Connection) -> None:
    """Las sesiones caducadas se borran al arrancar: dejarlas en la tabla es
    guardar credenciales validas para nada."""
    con.execute(
        "DELETE FROM sesiones WHERE ultimo_uso <= datetime('now', ?)",
        (f"-{DIAS_SESION} days",),
    )
    con.commit()


# Paletas que el usuario puede elegir. Vive aqui y no solo en el CSS para que
# nadie se guarde un tema inventado en la base.
TEMAS_VISUALES = ("papel", "noche", "bosque", "atardecer")


def cambiar_usuario(con: sqlite3.Connection, usuario_id: int, nuevo: str) -> str:
    if not USUARIO_VALIDO.match(nuevo or ""):
        raise DatosInvalidos(
            "El usuario necesita entre 3 y 32 caracteres, sin espacios"
            " (letras, numeros, punto, guion o guion bajo)."
        )
    try:
        con.execute("UPDATE usuarios SET usuario=? WHERE id=?", (nuevo, usuario_id))
    except sqlite3.IntegrityError as exc:
        raise UsuarioOcupado("Ese usuario ya existe.") from exc
    con.commit()
    return nuevo


def cambiar_clave(
    con: sqlite3.Connection, usuario_id: int, actual: str, nueva: str
) -> None:
    """Pide la clave de siempre aunque la sesion ya este abierta: un movil
    desbloqueado un momento no deberia bastar para quedarse con la cuenta."""
    fila = con.execute(
        "SELECT clave FROM usuarios WHERE id=?", (usuario_id,)
    ).fetchone()
    if fila is None or not comprobar(actual, fila["clave"]):
        raise CredencialesMalas("La contrasena actual no es correcta.")
    if len(nueva or "") < CLAVE_MINIMA:
        raise DatosInvalidos(
            f"La contrasena necesita al menos {CLAVE_MINIMA} caracteres."
        )
    con.execute("UPDATE usuarios SET clave=? WHERE id=?", (cifrar(nueva), usuario_id))
    con.commit()


def cerrar_otras_sesiones(
    con: sqlite3.Connection, usuario_id: int, conservar: str
) -> None:
    """Al cambiar la clave, las sesiones abiertas en otros sitios dejan de
    valer. La de aqui se conserva para no echar a quien acaba de cambiarla."""
    con.execute(
        "DELETE FROM sesiones WHERE usuario_id=? AND token!=?", (usuario_id, conservar)
    )
    con.commit()


def cambiar_tema(con: sqlite3.Connection, usuario_id: int, tema: str) -> str:
    if tema not in TEMAS_VISUALES:
        raise DatosInvalidos("Ese tema visual no existe.")
    con.execute("UPDATE usuarios SET tema_visual=? WHERE id=?", (tema, usuario_id))
    con.commit()
    return tema
