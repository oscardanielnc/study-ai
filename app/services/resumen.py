import re
import sqlite3

from app.llm.client import LLMClient, LLMError
from app.llm.contabilidad import registrar
from app.llm.prompts import prompt_resumen


# Tope del proveedor por respuesta. La extension la manda el prompt, no esto:
# recortar max_tokens no acorta el resumen, lo trunca.
MAX_TOKENS = 8000


def _pedir(llm: LLMClient, modelo: str, cuerpo: str, n_docs: int, palabras: int):
    """Pide el resumen, y si el modelo se queda sin presupuesto lo vuelve a
    pedir mas breve.

    Resumir no es razonar: con el razonamiento activo el modelo se gasto los
    8000 tokens pensando y devolvio texto vacio (finish_reason=length),
    tirando a la basura cinco transcripciones que habian salido perfectas.
    """
    for intento in (palabras, palabras // 2, palabras // 4):
        try:
            return llm.completar(
                modelo=modelo,
                sistema=prompt_resumen(n_docs, intento),
                usuario=cuerpo,
                max_tokens=MAX_TOKENS,
                sin_razonamiento=True,
            )
        except LLMError as exc:
            ultimo = exc
    raise ultimo


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
    resultado = _pedir(llm, modelo, cuerpo, len(filas), palabras)
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
