PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    clave     TEXT NOT NULL,
    creado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Un token por sesion. No caducan: en el movil, volver a pedir la contrasena
-- cada poco es lo que hace que la gente deje de abrir la app.
CREATE TABLE IF NOT EXISTS sesiones (
    token      TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creado_en  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS temas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id     INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    titulo         TEXT NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fuentes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_id         INTEGER NOT NULL REFERENCES temas(id) ON DELETE CASCADE,
    nombre_original TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('imagen', 'pdf')),
    transcripcion   TEXT NOT NULL,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resumen (
    tema_id      INTEGER PRIMARY KEY REFERENCES temas(id) ON DELETE CASCADE,
    contenido_md TEXT NOT NULL,
    modelo       TEXT NOT NULL,
    generado_en  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS preguntas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_id       INTEGER NOT NULL REFERENCES temas(id) ON DELETE CASCADE,
    nivel         TEXT NOT NULL CHECK (nivel IN ('facil','intermedio','dificil')),
    enunciado     TEXT NOT NULL,
    opciones_json TEXT NOT NULL,
    correcta_idx  INTEGER NOT NULL CHECK (correcta_idx BETWEEN 0 AND 3),
    justificacion TEXT NOT NULL,
    veces_vista   INTEGER NOT NULL DEFAULT 0,
    creado_en     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_preguntas_tema_nivel ON preguntas(tema_id, nivel);

CREATE TABLE IF NOT EXISTS examenes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_id      INTEGER NOT NULL REFERENCES temas(id) ON DELETE CASCADE,
    nivel        TEXT NOT NULL CHECK (nivel IN ('facil','intermedio','dificil')),
    iniciado_en  TEXT NOT NULL DEFAULT (datetime('now')),
    terminado_en TEXT,
    aciertos     INTEGER,
    total        INTEGER
);

CREATE TABLE IF NOT EXISTS respuestas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    examen_id   INTEGER NOT NULL REFERENCES examenes(id) ON DELETE CASCADE,
    pregunta_id INTEGER NOT NULL REFERENCES preguntas(id) ON DELETE CASCADE,
    elegida_idx INTEGER NOT NULL,
    correcta    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tema_id         INTEGER NOT NULL REFERENCES temas(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('transcribir','resumir','generar_preguntas')),
    estado          TEXT NOT NULL CHECK (estado IN ('pendiente','en_curso','completado','fallido')),
    progreso_actual INTEGER NOT NULL DEFAULT 0,
    progreso_total  INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    paso           TEXT NOT NULL,
    modelo         TEXT NOT NULL,
    tokens_in      INTEGER NOT NULL,
    tokens_out     INTEGER NOT NULL,
    costo_estimado REAL NOT NULL,
    creado_en      TEXT NOT NULL DEFAULT (datetime('now'))
);
