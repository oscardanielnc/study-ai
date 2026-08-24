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
separado{s} por encabezados "## Documento N de {n}".

Redacta con TODOS ellos un único resumen de estudio en Markdown:
- Un título de nivel 1 (#) breve y descriptivo del tema completo.
- Subtítulos (##) por cada bloque conceptual.
- Cubre TODOS los documentos. Ninguno puede quedar fuera ni reducirse a una
  línea: cada uno aporta contenido evaluable distinto.
- Condensa la redundancia, nunca el contenido. Si algo puede entrar en un
  examen, tiene que estar aquí: definiciones, cifras, clasificaciones,
  fórmulas, ejemplos y excepciones.
- Fórmulas en LaTeX ($ en línea, $$ en bloque).
- Una sección final "## Puntos clave" con viñetas.

Extensión objetivo: unas {objetivo} palabras. Quédate por debajo solo si los
apuntes de verdad no dan para más; nunca por comodidad.

Conserva las marcas [?] y los bloques [DIAGRAMA: ...] que encuentres.
Devuelve solo el Markdown."""


def prompt_resumen(n_documentos: int, palabras_entrada: int) -> str:
    """Sin un objetivo explicito el modelo escribe siempre lo mismo: cinco
    fotos daban un resumen igual de largo que una sola, comprimiendo cinco
    veces mas y tirando el 80% de lo estudiable. La extension tiene que
    seguir a la entrada."""
    objetivo = max(300, round(palabras_entrada * 0.7 / 50) * 50)
    return RESUMEN.format(
        n=n_documentos,
        s="" if n_documentos == 1 else "s",
        objetivo=objetivo,
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
