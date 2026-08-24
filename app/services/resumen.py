import re
import sqlite3

from app.llm.client import LLMClient
from app.llm.contabilidad import registrar
from app.llm.prompts import prompt_resumen


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

    # Numerados: sin separarlos el modelo lee un texto corrido y funde los
    # cinco documentos en el resumen generico de uno solo.
    cuerpo = "\n\n".join(
        f"## Documento {i} de {len(filas)}\n\n{f['transcripcion']}"
        for i, f in enumerate(filas, start=1)
    )
    palabras = len(cuerpo.split())
    resultado = llm.completar(
        modelo=modelo,
        sistema=prompt_resumen(len(filas), palabras),
        usuario=cuerpo,
        # El presupuesto de salida sigue al objetivo del prompt: con el tope
        # fijo de 8000 el modelo se cortaba a media frase en temas largos.
        # ~2,5 tokens por palabra, y 8000 es el maximo del proveedor.
        max_tokens=min(8000, max(2000, int(palabras * 0.7 * 2.5) + 500)),
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
