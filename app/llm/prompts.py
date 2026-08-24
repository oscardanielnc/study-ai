TRANSCRIPCION = """\
Eres un transcriptor de apuntes de clase. Transcribe la imagen a texto en español.

Reglas obligatorias:
1. Transcribe FIELMENTE. No resumas, no interpretes, no completes ideas.
2. Escribe las fórmulas matemáticas en LaTeX, entre $ para línea y $$ para bloque.
3. Los diagramas, gráficos y esquemas descríbelos entre corchetes con el prefijo
   [DIAGRAMA: ...], con detalle suficiente para estudiar sin ver la imagen.
4. Lo que NO puedas leer con seguridad márcalo [?]. NUNCA lo adivines: un dato
   inventado es peor que un hueco, porque la imagen original se borrará.
5. Conserva la estructura visual (títulos, listas, numeración).

Devuelve solo la transcripción, sin comentarios ni preámbulo.\
"""

RESUMEN = """Eres un profesor que prepara material de estudio en español.

Vas a recibir {n} documento{s} transcrito{s} de los apuntes de un alumno,
separado{s} por encabezados "## Documento N".{continua}

Redacta con TODOS ellos material de estudio en Markdown.

Que se va:
- La redundancia: lo mismo dicho dos veces, los rodeos, las frases de relleno,
  los ejemplos repetidos que no añaden nada nuevo.

Que se queda, sin excepcion:
- Definiciones, cifras, fechas, nombres, clasificaciones y sus criterios.
- Fórmulas (en LaTeX: $ en línea, $$ en bloque), con lo que significa cada
  símbolo.
- Procesos y sus pasos, causas y consecuencias, excepciones y casos limite.
- Cualquier cosa que pueda entrar en un examen.

Reglas:
{titulo}- Subtítulos (##) por cada bloque conceptual, en el orden de los apuntes.
- Cubre TODOS los documentos. Ninguno puede quedar fuera ni reducirse a una
  línea: cada uno aporta contenido distinto.
{cierre}- Conserva las marcas [?] y los bloques [DIAGRAMA: ...] que encuentres.

Extensión: unas {objetivo} palabras, algo más de la mitad de lo que recibes.
Es una guía, no un límite. Si el contenido da para más, escribe más: NUNCA
tires información para que quepa en una extensión. Solo se recorta lo que
sobra, nunca lo que se estudia.

Devuelve solo el Markdown."""

# Cuanto del original sobrevive. Los apuntes traen mucha repeticion, asi que
# por debajo de esto se empieza a perder materia; por encima, se copia.
RATIO = 0.55


def objetivo_palabras(palabras_entrada: int) -> int:
    """Sin un objetivo explicito el modelo escribe siempre lo mismo: cinco
    fotos daban un resumen igual de largo que una sola, comprimiendo cinco
    veces mas y tirando el 80% de lo estudiable. No hay techo: si el objetivo
    no cabe en una respuesta, `repartir` lo trocea en varias llamadas."""
    return max(300, round(palabras_entrada * RATIO / 50) * 50)


def prompt_resumen(
    n_documentos: int,
    palabras_entrada: int,
    primero: bool = True,
    ultimo: bool = True,
) -> str:
    """`primero`/`ultimo` marcan la posicion del bloque: solo el primero pone
    el titulo del tema y solo el ultimo cierra con los puntos clave."""
    return RESUMEN.format(
        n=n_documentos,
        s="" if n_documentos == 1 else "s",
        objetivo=objetivo_palabras(palabras_entrada),
        continua=(
            ""
            if primero
            else " Son la continuacion de unos apuntes que ya empezaste a resumir."
        ),
        titulo=(
            "- Empieza con un título de nivel 1 (#) breve y descriptivo del tema.\n"
            if primero
            else "- NO pongas titulo de nivel 1 (#): esto continua un resumen ya"
            " empezado.\n  Empieza directamente por un subtítulo (##).\n"
        ),
        cierre=(
            '- Cierra con una sección "## Puntos clave" con viñetas.\n'
            if ultimo
            else "- No cierres ni concluyas: el resumen sigue después.\n"
        ),
    )


_NIVELES = {
    "facil": (
        "FÁCIL: recuerdo directo. Definiciones y datos explícitos en el material."
    ),
    "intermedio": (
        "INTERMEDIO: aplicación. Relacionar dos conceptos, interpretar un caso "
        "o usar una fórmula."
    ),
    "dificil": (
        "DIFÍCIL: razonamiento en varios pasos, casos límite y aplicación a "
        "situaciones nuevas que no aparecen literalmente en los apuntes."
    ),
}

PREGUNTAS = """\
Eres un profesor que redacta exámenes de opción múltiple en español.

Genera exactamente {n} preguntas de nivel {nivel_desc}

Reglas obligatorias:
1. Exactamente 4 opciones por pregunta y exactamente 1 correcta.
2. Los distractores deben ser PLAUSIBLES y de longitud similar a la correcta.
   Nunca hagas que la opción correcta sea la más larga o la más detallada.
3. Prohibido preguntar "según el texto..." o "el documento menciona...".
   Se evalúa el concepto, no la memoria del documento.
4. Toda pregunta lleva justificacion explicando por qué la correcta lo es.
   En matemáticas, breve y con LaTeX.
5. No uses contenido marcado [?]: es material ilegible.

Devuelve SOLO un objeto JSON válido, sin markdown ni ```:
{{"preguntas": [{{"enunciado": "...", "opciones": ["a","b","c","d"],
"correcta_idx": 0, "justificacion": "..."}}]}}\
"""


def prompt_preguntas(nivel: str, n: int) -> str:
    return PREGUNTAS.format(n=n, nivel_desc=_NIVELES[nivel])
