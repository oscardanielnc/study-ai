import pytest

from app.db import conectar
from app.llm.fake import FakeLLMClient
from app.services.resumen import extraer_titulo, generar_resumen

MD = "# Ley de Ohm\n\n## Enunciado\n\n$V = IR$\n\n## Puntos clave\n\n- Uno\n"


@pytest.fixture
def con(tmp_path):
    con = conectar(str(tmp_path / "t.db"))
    con.execute("INSERT INTO temas (id, titulo) VALUES (1, 'Sin titulo')")
    for i, t in enumerate(["Parte A", "Parte B"]):
        con.execute(
            "INSERT INTO fuentes (tema_id, nombre_original, tipo, transcripcion)"
            " VALUES (1, ?, 'imagen', ?)",
            (f"f{i}.jpg", t),
        )
    con.commit()
    return con


def test_extraer_titulo_toma_el_h1():
    assert extraer_titulo(MD) == "Ley de Ohm"


def test_extraer_titulo_devuelve_none_sin_h1():
    assert extraer_titulo("sin encabezado") is None


def test_guarda_el_resumen_en_la_bd(con):
    generar_resumen(con, FakeLLMClient([MD]), "m", 1)
    fila = con.execute("SELECT contenido_md FROM resumen WHERE tema_id=1").fetchone()
    assert fila["contenido_md"] == MD.strip()


def test_actualiza_el_titulo_del_tema(con):
    generar_resumen(con, FakeLLMClient([MD]), "m", 1)
    fila = con.execute("SELECT titulo FROM temas WHERE id=1").fetchone()
    assert fila["titulo"] == "Ley de Ohm"


def test_envia_todas_las_fuentes_al_modelo(con):
    fake = FakeLLMClient([MD])
    generar_resumen(con, fake, "m", 1)
    enviado = fake.llamadas[0]["usuario"]
    assert "Parte A" in enviado and "Parte B" in enviado


def test_regenerar_reemplaza_en_vez_de_duplicar(con):
    generar_resumen(con, FakeLLMClient([MD]), "m", 1)
    generar_resumen(con, FakeLLMClient(["# Otro\n"]), "m", 1)
    assert con.execute("SELECT COUNT(*) FROM resumen").fetchone()[0] == 1


def test_falla_si_el_tema_no_tiene_fuentes(tmp_path):
    con = conectar(str(tmp_path / "v.db"))
    con.execute("INSERT INTO temas (id, titulo) VALUES (9, 'Vacio')")
    con.commit()
    with pytest.raises(ValueError):
        generar_resumen(con, FakeLLMClient([MD]), "m", 9)
