import json
import re
import sqlite3
from collections.abc import Callable

from pydantic import ValidationError

from app.llm.client import LLMClient
from app.llm.contabilidad import registrar
from app.llm.prompts import prompt_preguntas
from app.models import LotePreguntas, Nivel

_VALLA = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")
# Escapes JSON que respetamos tal cual. Deliberadamente NO incluye \f ni \b:
# en apuntes, "\frac" y "\beta" son LaTeX constante, mientras que un form feed
# o un backspace literales no tienen ningun uso legitimo en este contenido.
_ESCAPES_RESPETADOS = '"/nrtu'


def reparar_latex(texto: str) -> str:
    """Dobla las barras que el modelo dejo sin escapar dentro del JSON.

    Los modelos escriben LaTeX crudo ("$\\Omega$", "$\\frac{a}{b}$") dentro de
    las cadenas JSON. Unas veces es JSON invalido y otras, peor todavia, es
    valido pero se decodifica a un caracter de control. Un "\\\\" ya correcto
    se copia intacto, de modo que aplicarlo a JSON bien formado no lo altera.
    """
    salida: list[str] = []
    i = 0
    while i < len(texto):
        c = texto[i]
        if c == "\\" and i + 1 < len(texto):
            siguiente = texto[i + 1]
            if siguiente == "\\" or siguiente in _ESCAPES_RESPETADOS:
                salida.append(texto[i : i + 2])
            else:
                salida.append("\\\\" + siguiente)
            i += 2
        else:
            salida.append(c)
            i += 1
    return "".join(salida)


def parsear_lote(texto: str) -> LotePreguntas:
    limpio = reparar_latex(_VALLA.sub("", texto.strip()))
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON de preguntas invalido: {exc}") from exc
    try:
        return LotePreguntas(**datos)
    except (ValidationError, TypeError) as exc:
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


# Tope por llamada. Medido con el modelo real: una pregunta dificil ronda los
# 1.200 tokens de salida, asi que un lote de 20 desbordaba max_tokens y volvia
# el JSON invalido. Diez deja margen de sobra.
LOTE_MAX = 10


def generar(
    con: sqlite3.Connection,
    llm: LLMClient,
    modelo: str,
    tema_id: int,
    nivel: Nivel,
    cantidad: int,
    lote: int = LOTE_MAX,
    avance: Callable[[int], None] | None = None,
) -> int:
    """Genera `cantidad` preguntas troceando en llamadas de `lote` como maximo."""
    hechas = 0
    while hechas < cantidad:
        pedir = min(lote, cantidad - hechas)
        hechas += generar_lote(con, llm, modelo, tema_id, nivel, pedir)
        if avance:
            avance(hechas)
    return hechas
