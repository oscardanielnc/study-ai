import sqlite3
from dataclasses import dataclass

from app.config import Settings
from app.ingest.pdfs import contar_paginas, es_digital, extraer_texto, rasterizar
from app.llm.client import LLMClient
from app.llm.contabilidad import dueno_del_tema
from app.services.auth import limpiar_sesiones
from app.services.resumen import generar_resumen
from app.services.transcribe import transcribir_imagen


@dataclass
class Archivo:
    nombre: str
    datos: bytes


def crear_job(con: sqlite3.Connection, tema_id: int, n_archivos: int) -> int:
    """El resumen cuenta como un paso mas: si no, la barra se clava al 100%
    durante los ~30 s que tarda en escribirlo."""
    cur = con.execute(
        "INSERT INTO jobs (tema_id, tipo, estado, progreso_total)"
        " VALUES (?, 'transcribir', 'pendiente', ?)",
        (tema_id, n_archivos + 1),
    )
    con.commit()
    return int(cur.lastrowid)


def marcar_interrumpidos(con: sqlite3.Connection) -> None:
    """Al arrancar, los jobs a medias son de un proceso que ya no existe.
    Nadie los va a retomar, asi que se cierran en falso en vez de dejar al
    cliente sondeando para siempre."""
    con.execute(
        "UPDATE jobs SET estado='fallido',"
        " error='Se interrumpio el servidor a mitad del proceso.'"
        " WHERE estado IN ('pendiente','en_curso')"
    )
    con.commit()


def limpiar_basura(con: sqlite3.Connection) -> None:
    """Tira los temas que nunca llegaron a tener resumen.

    Un fallo a mitad dejaba una tarjeta 'Procesando...' cuyo unico contenido
    era 'Sin resumen'. Eso no es un tema a medias, es basura: el error ya se
    le conto al usuario y las transcripciones sueltas no le sirven de nada.
    Se respeta lo que aun se esta procesando.
    """
    limpiar_sesiones(con)
    con.execute(
        "DELETE FROM temas WHERE id NOT IN (SELECT tema_id FROM resumen)"
        " AND id NOT IN (SELECT tema_id FROM jobs"
        " WHERE estado IN ('pendiente','en_curso'))"
    )
    con.commit()


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
    dueno = dueno_del_tema(con, tema_id)

    for i, archivo in enumerate(archivos, start=1):
        try:
            if archivo.nombre.lower().endswith(".pdf"):
                texto = extraer_texto(archivo.datos)
                if not es_digital(texto, contar_paginas(archivo.datos)):
                    # PDF escaneado: sin texto embebido. Pillow no abre PDFs,
                    # asi que rasterizamos cada pagina antes de mandarla a vision.
                    texto = "\n\n".join(
                        transcribir_imagen(
                            con, llm, settings.modelo_transcripcion, pagina, dueno
                        )
                        for pagina in rasterizar(archivo.datos)
                    )
                _guardar_fuente(con, tema_id, archivo.nombre, "pdf", texto)
            else:
                texto = transcribir_imagen(
                    con, llm, settings.modelo_transcripcion, archivo.datos, dueno
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

    def resumen_avanza(hechos: int, bloques: int) -> None:
        # El resumen puede necesitar varias llamadas: el total no se sabe
        # hasta tener las transcripciones, asi que se corrige aqui.
        con.execute(
            "UPDATE jobs SET progreso_actual=?, progreso_total=? WHERE id=?",
            (len(archivos) + hechos, len(archivos) + bloques, job_id),
        )
        con.commit()

    try:
        generar_resumen(
            con, llm, settings.modelo_resumen, tema_id, avance=resumen_avanza
        )
    except Exception as exc:
        con.execute(
            "UPDATE jobs SET estado='fallido', error=? WHERE id=?",
            (f"resumen: {exc}", job_id),
        )
        con.commit()
        return

    con.execute(
        "UPDATE jobs SET estado='completado', progreso_actual=progreso_total"
        " WHERE id=?",
        (job_id,),
    )
    con.commit()
