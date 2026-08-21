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

RESUMEN = """\
Eres un profesor que prepara material de estudio en español.

A partir de las transcripciones de apuntes que recibirás, redacta un resumen
condensado y bien estructurado en Markdown:
- Un título de nivel 1 (#) breve y descriptivo del tema.
- Subtítulos (##) por cada bloque conceptual.
- Párrafos condensados: elimina la redundancia, conserva todo lo evaluable.
- Fórmulas en LaTeX ($ en línea, $$ en bloque).
- Una sección final "## Puntos clave" con viñetas.

Conserva las marcas [?] y los bloques [DIAGRAMA: ...] que encuentres.
Devuelve solo el Markdown.\
"""

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
