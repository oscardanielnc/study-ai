import math
import re
import sqlite3
from collections.abc import Callable

from app.llm.client import LLMClient, LLMError, LLMResult
from app.llm.contabilidad import registrar
from app.llm.prompts import RATIO, prompt_resumen

# Tope del proveedor por respuesta y lo que eso da de si en espanol (~3 tokens
# por palabra contando el Markdown y el LaTeX). NO es un techo del resumen:
# cuando el objetivo no cabe, `repartir` lo trocea en varias llamadas y las
# cose. Un resumen de 8.000 palabras sale de cuatro llamadas, no de una
# truncada.
MAX_TOKENS = 8000
PALABRAS_POR_RESPUESTA = 2400


def extraer_titulo(md: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    return m.group(1).strip() if m else None


def _trocear(texto: str, partes: int) -> list[str]:
    """Parte un documento largo. Solo hace falta cuando un unico documento ya
    pide mas de lo que cabe en una respuesta.

    Se corta por parrafos, y si no los hay bastantes, por lineas; en ultimo
    caso por palabras, que es feo pero nunca pierde texto.
    """
    if partes <= 1:
        return [texto]
    for sep in ("\n\n", "\n"):
        piezas = [t for t in texto.split(sep) if t.strip()]
        if len(piezas) >= partes:
            cada = math.ceil(len(piezas) / partes)
            return [
                sep.join(piezas[i : i + cada]) for i in range(0, len(piezas), cada)
            ]
    palabras = texto.split()
    cada = math.ceil(len(palabras) / partes)
    return [
        " ".join(palabras[i : i + cada]) for i in range(0, len(palabras), cada)
    ]


def repartir(
    textos: list[str], por_respuesta: int = PALABRAS_POR_RESPUESTA
) -> list[list[str]]:
    """Agrupa los documentos en bloques que quepan, cada uno, en una respuesta.

    Se conserva el orden: el resumen cosido tiene que seguir el hilo de los
    apuntes, no saltar de un tema a otro.
    """
    sueltos: list[str] = []
    for t in textos:
        cuantas = math.ceil(len(t.split()) * RATIO / por_respuesta)
        sueltos.extend(_trocear(t, cuantas))

    bloques: list[list[str]] = []
    actual: list[str] = []
    pedido = 0.0
    for t in sueltos:
        cuesta = len(t.split()) * RATIO
        if actual and pedido + cuesta > por_respuesta:
            bloques.append(actual)
            actual, pedido = [], 0.0
        actual.append(t)
        pedido += cuesta
    if actual:
        bloques.append(actual)
    return bloques


def _pedir(
    llm: LLMClient,
    modelo: str,
    cuerpo: str,
    n_docs: int,
    palabras: int,
    primero: bool,
    ultimo: bool,
) -> LLMResult:
    """Pide un bloque, y si el modelo se queda sin presupuesto lo vuelve a
    pedir mas breve.

    Resumir no es razonar: con el razonamiento activo el modelo se gasto los
    8000 tokens pensando y devolvio texto vacio (finish_reason=length),
    tirando a la basura cinco transcripciones que habian salido perfectas.
    """
    ultimo_fallo: Exception | None = None
    for intento in (palabras, int(palabras * 0.7), int(palabras * 0.5)):
        try:
            return llm.completar(
                modelo=modelo,
                sistema=prompt_resumen(n_docs, intento, primero, ultimo),
                usuario=cuerpo,
                max_tokens=MAX_TOKENS,
                sin_razonamiento=True,
            )
        except LLMError as exc:
            ultimo_fallo = exc
    raise ultimo_fallo  # type: ignore[misc]


def generar_resumen(
    con: sqlite3.Connection,
    llm: LLMClient,
    modelo: str,
    tema_id: int,
    avance: Callable[[int, int], None] | None = None,
) -> str:
    filas = con.execute(
        "SELECT transcripcion FROM fuentes WHERE tema_id=? ORDER BY id",
        (tema_id,),
    ).fetchall()
    if not filas:
        raise ValueError(f"El tema {tema_id} no tiene fuentes que resumir")

    bloques = repartir([f["transcripcion"] for f in filas])
    total_docs = sum(len(b) for b in bloques)

    partes: list[str] = []
    hecho = 0
    for i, bloque in enumerate(bloques):
        # Numerados y con el total global: sin separarlos el modelo lee un
        # texto corrido y funde los documentos en el resumen generico de uno.
        cuerpo = "\n\n".join(
            f"## Documento {hecho + k + 1} de {total_docs}\n\n{t}"
            for k, t in enumerate(bloque)
        )
        resultado = _pedir(
            llm,
            modelo,
            cuerpo,
            len(bloque),
            len(cuerpo.split()),
            primero=i == 0,
            ultimo=i == len(bloques) - 1,
        )
        registrar(con, "resumen", resultado)
        partes.append(resultado.texto.strip())
        hecho += len(bloque)
        if avance:
            avance(i + 1, len(bloques))

    md = "\n\n".join(partes)
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
