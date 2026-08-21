import json
import re
import sqlite3

from pydantic import ValidationError

from app.llm.client import LLMClient
from app.llm.contabilidad import registrar
from app.llm.prompts import prompt_preguntas
from app.models import LotePreguntas, Nivel

_VALLA = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parsear_lote(texto: str) -> LotePreguntas:
    limpio = _VALLA.sub("", texto.strip())
    try:
        return LotePreguntas(**json.loads(limpio))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ValueError(f"JSON de preguntas invalido: {exc}") from exc


def generar_lote(
    con: sqlite3.Connection,
    llm: LLMClient,
    modelo: str,
    tema_id: int,
    nivel: Nivel,
    n: int = 20,
) -> int:
    """Genera y guarda un lote. Un reintento ante JSON invalido, luego falla."""
    filas = con.execute(
        "SELECT transcripcion FROM fuentes WHERE tema_id=? ORDER BY id",
        (tema_id,),
    ).fetchall()
    if not filas:
        raise ValueError(f"El tema {tema_id} no tiene fuentes")
    cuerpo = "\n\n---\n\n".join(f["transcripcion"] for f in filas)

    ultimo: Exception | None = None
    for _ in range(2):
        resultado = llm.completar(
            modelo=modelo,
            sistema=prompt_preguntas(nivel, n),
            usuario=cuerpo,
            max_tokens=16000,
        )
        registrar(con, f"preguntas_{nivel}", resultado)
        try:
            lote = parsear_lote(resultado.texto)
            break
        except ValueError as exc:
            ultimo = exc
    else:
        raise ValueError(f"El modelo no devolvio JSON valido en 2 intentos: {ultimo}")

    con.executemany(
        "INSERT INTO preguntas (tema_id, nivel, enunciado, opciones_json,"
        " correcta_idx, justificacion) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                tema_id,
                nivel,
                p.enunciado,
                json.dumps(p.opciones, ensure_ascii=False),
                p.correcta_idx,
                p.justificacion,
            )
            for p in lote.preguntas
        ],
    )
    con.commit()
    return len(lote.preguntas)
