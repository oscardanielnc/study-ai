import pytest

from app.db import conectar
from app.services.auth import (
    CredencialesMalas,
    DatosInvalidos,
    UsuarioOcupado,
    cifrar,
    comprobar,
    entrar,
    registrar,
    salir,
    usuario_de_token,
)


@pytest.fixture
def con(tmp_path):
    return conectar(str(tmp_path / "t.db"))


def test_la_clave_no_se_guarda_en_claro():
    guardado = cifrar("secreta123")
    assert "secreta123" not in guardado
    assert comprobar("secreta123", guardado)
    assert not comprobar("otra", guardado)


def test_dos_veces_la_misma_clave_da_hashes_distintos():
    """Sin sal, dos usuarios con la misma clave se delatan entre si."""
    assert cifrar("igual123") != cifrar("igual123")


def test_un_hash_corrupto_no_revienta():
    assert not comprobar("x", "basura")


def test_registrarse_devuelve_una_sesion_usable(con):
    token = registrar(con, "oscar", "clave123")
    assert usuario_de_token(con, token)["usuario"] == "oscar"


def test_no_se_puede_repetir_usuario(con):
    registrar(con, "oscar", "clave123")
    with pytest.raises(UsuarioOcupado):
        registrar(con, "oscar", "otra12345")


@pytest.mark.parametrize(
    "usuario,clave",
    [("ab", "clave123"), ("con espacio", "clave123"), ("oscar", "corta")],
)
def test_se_rechazan_credenciales_pobres(con, usuario, clave):
    with pytest.raises(DatosInvalidos):
        registrar(con, usuario, clave)


def test_entrar_con_la_clave_correcta(con):
    registrar(con, "oscar", "clave123")
    assert usuario_de_token(con, entrar(con, "oscar", "clave123"))["usuario"] == "oscar"


def test_entrar_con_la_clave_mala(con):
    registrar(con, "oscar", "clave123")
    with pytest.raises(CredencialesMalas):
        entrar(con, "oscar", "clave124")


def test_entrar_con_un_usuario_que_no_existe(con):
    with pytest.raises(CredencialesMalas):
        entrar(con, "nadie", "clave123")


def test_un_token_inventado_no_vale(con):
    assert usuario_de_token(con, "inventado") is None
    assert usuario_de_token(con, "") is None


def test_salir_invalida_el_token(con):
    token = registrar(con, "oscar", "clave123")
    salir(con, token)
    assert usuario_de_token(con, token) is None


def test_cada_sesion_tiene_su_token(con):
    """Entrar desde el movil no puede cerrar la sesion del portatil."""
    uno = registrar(con, "oscar", "clave123")
    otro = entrar(con, "oscar", "clave123")
    assert uno != otro
    assert usuario_de_token(con, uno) is not None
