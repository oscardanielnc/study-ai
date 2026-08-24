import pytest

from app.db import conectar
from app.services.auth import (
    CredencialesMalas,
    DatosInvalidos,
    UsuarioOcupado,
    cambiar_clave,
    cambiar_tema,
    cambiar_usuario,
    cerrar_otras_sesiones,
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


# ---------- Perfil ----------


def test_cambiar_el_nombre_de_usuario(con):
    token = registrar(con, "oscar", "clave123")
    cambiar_usuario(con, 1, "oscar.navarro")
    assert usuario_de_token(con, token)["usuario"] == "oscar.navarro"
    assert entrar(con, "oscar.navarro", "clave123")


def test_no_se_puede_robar_el_nombre_de_otro(con):
    registrar(con, "oscar", "clave123")
    registrar(con, "ana", "clave123")
    with pytest.raises(UsuarioOcupado):
        cambiar_usuario(con, 2, "oscar")


def test_un_nombre_invalido_se_rechaza(con):
    registrar(con, "oscar", "clave123")
    with pytest.raises(DatosInvalidos):
        cambiar_usuario(con, 1, "con espacio")


def test_cambiar_la_clave_pide_la_de_siempre(con):
    registrar(con, "oscar", "clave123")
    with pytest.raises(CredencialesMalas):
        cambiar_clave(con, 1, "equivocada", "nueva123")


def test_cambiar_la_clave_deja_entrar_con_la_nueva(con):
    registrar(con, "oscar", "clave123")
    cambiar_clave(con, 1, "clave123", "nueva1234")
    with pytest.raises(CredencialesMalas):
        entrar(con, "oscar", "clave123")
    assert entrar(con, "oscar", "nueva1234")


def test_la_clave_nueva_tambien_tiene_minimo(con):
    registrar(con, "oscar", "clave123")
    with pytest.raises(DatosInvalidos):
        cambiar_clave(con, 1, "clave123", "abc")


def test_cambiar_la_clave_cierra_las_otras_sesiones(con):
    """Si alguien te la habia visto, cambiarla tiene que servir de algo."""
    viejo = registrar(con, "oscar", "clave123")
    actual = entrar(con, "oscar", "clave123")
    cambiar_clave(con, 1, "clave123", "nueva1234")
    cerrar_otras_sesiones(con, 1, actual)
    assert usuario_de_token(con, viejo) is None
    assert usuario_de_token(con, actual) is not None


def test_el_tema_visual_por_defecto_es_papel(con):
    registrar(con, "oscar", "clave123")
    fila = con.execute("SELECT tema_visual FROM usuarios WHERE id=1").fetchone()
    assert fila["tema_visual"] == "papel"


def test_se_puede_elegir_otro_tema_visual(con):
    registrar(con, "oscar", "clave123")
    assert cambiar_tema(con, 1, "noche") == "noche"


def test_un_tema_visual_inventado_no_se_guarda(con):
    registrar(con, "oscar", "clave123")
    with pytest.raises(DatosInvalidos):
        cambiar_tema(con, 1, "arcoiris")
