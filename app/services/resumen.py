import re
import sqlite3

from app.llm.client import LLMClient
from app.llm.contabilidad import registrar
from app.llm.prompts import RESUMEN


def extraer_titulo(md: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    return m.group(1).strip() if m else None


def generar_resumen(
    con: sqlite3.Connection,
    llm: LLMClient,
    modelo: str,
    tema_id: int,
) -> str:
    filas = con.execute(
        "SELECT transcripcion FROM fuentes WHERE tema_id=? ORDER BY id",
        (tema_id,),
    ).fetchall()
    if not filas:
        raise ValueError(f"El tema {tema_id} no tiene fuentes que resumir")

    cuerpo = "\n\n---\n\n".join(f["transcripcion"] for f in filas)
    resultado = llm.completar(
        modelo=modelo,
        sistema=RESUMEN,
        usuario=cuerpo,
        max_tokens=8000,
    )
    registrar(con, "resumen", resultado)
    md = resultado.texto.strip()

    con.execute(
        "INSERT OR REPLACE INTO resumen (tema_id, contenido_md, modelo, generado_en)"
        " VALUES (?, ?, ?, datetime('now'))",
        (tema_id, md, modelo),
    )
    titulo = extraer_titulo(md)
    if titulo:
        con.execute(
            "UPDATE temas SET titulo=?, actualizado_en=datetime('now') WHERE id=?",
            (titulo, tema_id),
        )
    con.commit()
    return md
