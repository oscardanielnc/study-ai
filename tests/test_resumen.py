import re

import pytest

from app.db import conectar
from app.llm.client import LLMError
from app.llm.fake import FakeLLMClient
from app.llm.prompts import RATIO, prompt_resumen
from app.services.resumen import (
    PALABRAS_POR_RESPUESTA,
    extraer_titulo,
    generar_resumen,
    repartir,
)

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


# ---------- Extension proporcional a los apuntes ----------


def _objetivo(prompt: str) -> int:
    return int(re.search(r"unas (\d+) palabras", prompt).group(1))


def test_el_objetivo_de_extension_crece_con_los_apuntes():
    """Cinco fotos daban el mismo resumen que una: el modelo, sin objetivo,
    escribe siempre lo mismo y comprime cinco veces mas."""
    assert _objetivo(prompt_resumen(1, 800)) < _objetivo(prompt_resumen(5, 4000))


def test_el_objetivo_tiene_un_suelo_para_apuntes_minusculos():
    assert _objetivo(prompt_resumen(1, 20)) >= 300


def test_el_prompt_dice_cuantos_documentos_llegan():
    assert "5 documentos" in prompt_resumen(5, 4000)


def test_el_cuerpo_numera_los_documentos(con):
    """Sin separarlos, el modelo lee un texto corrido y funde los temas."""
    llm = FakeLLMClient([MD])
    generar_resumen(con, llm, "m", 1)
    usuario = llm.llamadas[0]["usuario"]
    assert "## Documento 1 de 2" in usuario
    assert "## Documento 2 de 2" in usuario


def test_el_resumen_no_razona():
    """Con el razonamiento activo el modelo gasto los 8000 tokens pensando y
    devolvio texto vacio (finish_reason=length). Resumir es reescribir."""
    con = _con_fuentes()
    llm = FakeLLMClient([MD])
    generar_resumen(con, llm, "m", 1)
    assert llm.llamadas[0]["sin_razonamiento"] is True


def test_el_objetivo_no_tiene_techo():
    """Con 10.000 palabras de apuntes el resumen tiene que ser de miles de
    palabras, no recortarse para caber en una sola llamada."""
    assert _objetivo(prompt_resumen(20, 10000)) >= 4000


def test_reintenta_mas_corto_si_el_modelo_se_queda_sin_presupuesto():
    """Cinco fotos transcritas bien no pueden tirarse a la basura porque el
    resumen se paso de largo: se vuelve a pedir mas breve."""
    con = _con_fuentes()
    llm = _LlmQueFallaLaPrimera(MD)
    generar_resumen(con, llm, "m", 1)
    assert len(llm.llamadas) == 2
    assert _objetivo(llm.llamadas[1]["sistema"]) < _objetivo(llm.llamadas[0]["sistema"])


class _LlmQueFallaLaPrimera(FakeLLMClient):
    def __init__(self, respuesta):
        super().__init__([respuesta])
        self._fallado = False

    def completar(self, **kw):
        if not self._fallado:
            self._fallado = True
            self.llamadas.append(kw)
            raise LLMError("El modelo devolvio una respuesta vacia")
        return super().completar(**kw)


def _con_fuentes(*textos):
    from app.db import conectar
    import tempfile, pathlib as _p
    d = tempfile.mkdtemp()
    con = conectar(str(_p.Path(d) / "t.db"))
    con.execute("INSERT INTO temas (id, titulo) VALUES (1, 'Sin titulo')")
    for i, t in enumerate(textos or ("Parte A " * 200, "Parte B " * 200)):
        con.execute(
            "INSERT INTO fuentes (tema_id, nombre_original, tipo, transcripcion)"
            " VALUES (1, ?, 'imagen', ?)",
            (f"f{i}.jpg", t),
        )
    con.commit()
    return con


# ---------- Reparto en bloques ----------


def _palabras(n):
    return " ".join(["palabra"] * n)


def test_lo_que_cabe_en_una_respuesta_va_en_un_solo_bloque():
    assert len(repartir([_palabras(500), _palabras(400)])) == 1


def test_lo_que_no_cabe_se_reparte_en_varias_llamadas():
    """Una respuesta del proveedor no da para 5.500 palabras: si no se
    reparte, el resumen sale truncado o vacio."""
    bloques = repartir([_palabras(4000) for _ in range(3)])
    assert len(bloques) >= 3


def test_ningun_bloque_pide_mas_de_lo_que_cabe():
    for bloque in repartir([_palabras(9000), _palabras(300)]):
        pedido = sum(len(t.split()) for t in bloque) * RATIO
        assert pedido <= PALABRAS_POR_RESPUESTA * 1.05


def test_un_documento_enorme_se_trocea_sin_perder_texto():
    doc = "\n\n".join(_palabras(300) for _ in range(30))
    trozos = [t for bloque in repartir([doc]) for t in bloque]
    assert len(trozos) > 1
    assert sum(len(t.split()) for t in trozos) == 9000


def test_solo_el_primer_bloque_pone_titulo():
    con = _con_fuentes(_palabras(4000), _palabras(4000))
    llm = FakeLLMClient([MD, "## Mas\n\ntexto"] * 4)
    generar_resumen(con, llm, "m", 1)
    assert len(llm.llamadas) >= 2
    assert "Empieza con un título de nivel 1" in llm.llamadas[0]["sistema"]
    assert "NO pongas titulo" in llm.llamadas[1]["sistema"]


def test_el_resumen_por_bloques_se_cose_entero():
    con = _con_fuentes(_palabras(4000), _palabras(4000))
    llm = FakeLLMClient(["# T\n\n## A\n\nuno", "## B\n\ndos"] * 4)
    md = generar_resumen(con, llm, "m", 1)
    assert "## A" in md and "## B" in md


def test_avisa_del_avance_por_bloque():
    con = _con_fuentes(_palabras(4000), _palabras(4000))
    vistos = []
    generar_resumen(
        con,
        FakeLLMClient(["# T\n\ntexto", "## B\n\ndos"] * 4),
        "m",
        1,
        avance=lambda hechos, total: vistos.append((hechos, total)),
    )
    assert vistos[-1][0] == vistos[-1][1] >= 2
