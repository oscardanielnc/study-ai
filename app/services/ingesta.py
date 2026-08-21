import sqlite3
from dataclasses import dataclass

from app.config import Settings
from app.ingest.pdfs import contar_paginas, es_digital, extraer_texto, rasterizar
from app.llm.client import LLMClient
from app.services.resumen import generar_resumen
from app.services.transcribe import transcribir_imagen


@dataclass
class Archivo:
    nombre: str
    datos: bytes


def crear_job(con: sqlite3.Connection, tema_id: int, total: int) -> int:
    cur = con.execute(
        "INSERT INTO jobs (tema_id, tipo, estado, progreso_total)"
        " VALUES (?, 'transcribir', 'pendiente', ?)",
        (tema_id, total),
    )
    con.commit()
    return int(cur.lastrowid)


def _guardar_fuente(
    con: sqlite3.Connection, tema_id: int, nombre: str, tipo: str, texto: str
) -> None:
    con.execute(
        "INSERT INTO fuentes (tema_id, nombre_original, tipo, transcripcion)"
        " VALUES (?, ?, ?, ?)",
        (tema_id, nombre, tipo, texto),
    )
    con.commit()


def procesar(
    con: sqlite3.Connection,
    llm: LLMClient,
    settings: Settings,
    tema_id: int,
    job_id: int,
    archivos: list[Archivo],
) -> None:
    """Transcribe todo y resume. Los bytes se descartan al salir de esta funcion:
    lo que sobrevive es la fila en `fuentes`, escrita archivo a archivo."""
    con.execute("UPDATE jobs SET estado='en_curso' WHERE id=?", (job_id,))
    con.commit()

    for i, archivo in enumerate(archivos, start=1):
        try:
            if archivo.nombre.lower().endswith(".pdf"):
                texto = extraer_texto(archivo.datos)
                if not es_digital(texto, contar_paginas(archivo.datos)):
                    # PDF escaneado: sin texto embebido. Pillow no abre PDFs,
                    # asi que rasterizamos cada pagina antes de mandarla a vision.
                    texto = "\n\n".join(
                        transcribir_imagen(
                            con, llm, settings.modelo_transcripcion, pagina
                        )
                        for pagina in rasterizar(archivo.datos)
                    )
                _guardar_fuente(con, tema_id, archivo.nombre, "pdf", texto)
            else:
                texto = transcribir_imagen(
                    con, llm, settings.modelo_transcripcion, archivo.datos
                )
                _guardar_fuente(con, tema_id, archivo.nombre, "imagen", texto)
        except Exception as exc:
            con.execute(
                "UPDATE jobs SET estado='fallido', error=? WHERE id=?",
                (f"{archivo.nombre}: {exc}", job_id),
            )
            con.commit()
            return

        con.execute("UPDATE jobs SET progreso_actual=? WHERE id=?", (i, job_id))
        con.commit()

    try:
        generar_resumen(con, llm, settings.modelo_resumen, tema_id)
    except Exception as exc:
        con.execute(
            "UPDATE jobs SET estado='fallido', error=? WHERE id=?",
            (f"resumen: {exc}", job_id),
        )
        con.commit()
        return

    con.execute("UPDATE jobs SET estado='completado' WHERE id=?", (job_id,))
    con.commit()
