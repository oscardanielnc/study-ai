import sqlite3

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm.client import LLMClient
from app.llm.contabilidad import TopeSuperado, gasto_del_mes, verificar_tope
from app.models import Nivel
from app.services import examen as svc_examen
from app.services.ingesta import Archivo, crear_job, procesar
from app.services.preguntas import LOTE_MAX, generar

CANTIDADES = (10, 20, 30, 40)


class NivelBody(BaseModel):
    nivel: Nivel


class ExamenBody(BaseModel):
    nivel: Nivel
    cantidad: int = Field(ge=1, le=max(CANTIDADES))


class RespuestaBody(BaseModel):
    pregunta_id: int
    elegida_idx: int


def crear_router(
    con: sqlite3.Connection, llm: LLMClient, settings: Settings
) -> APIRouter:
    r = APIRouter(prefix="/api")

    async def _leer(archivos: list[UploadFile]) -> list[Archivo]:
        return [Archivo(a.filename or "sin-nombre", await a.read()) for a in archivos]

    @r.get("/temas")
    def listar_temas():
        filas = con.execute(
            "SELECT t.id, t.titulo, t.actualizado_en,"
            " (SELECT COUNT(*) FROM fuentes f WHERE f.tema_id=t.id) AS n_fuentes"
            " FROM temas t ORDER BY t.actualizado_en DESC"
        ).fetchall()
        return [dict(f) for f in filas]

    @r.post("/temas")
    async def crear_tema(fondo: BackgroundTasks, archivos: list[UploadFile]):
        try:
            verificar_tope(con, settings.tope_gasto_mensual_usd)
        except TopeSuperado as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc

        cur = con.execute("INSERT INTO temas (titulo) VALUES ('Procesando...')")
        tema_id = int(cur.lastrowid)
        con.commit()

        datos = await _leer(archivos)
        job_id = crear_job(con, tema_id, len(datos))
        fondo.add_task(procesar, con, llm, settings, tema_id, job_id, datos)
        return {"tema_id": tema_id, "job_id": job_id}

    @r.post("/temas/{tema_id}/material")
    async def anadir_material(
        tema_id: int, fondo: BackgroundTasks, archivos: list[UploadFile]
    ):
        if con.execute("SELECT 1 FROM temas WHERE id=?", (tema_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Tema no encontrado")
        datos = await _leer(archivos)
        job_id = crear_job(con, tema_id, len(datos))
        fondo.add_task(procesar, con, llm, settings, tema_id, job_id, datos)
        return {"job_id": job_id}

    @r.get("/jobs/{job_id}")
    def ver_job(job_id: int):
        f = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if f is None:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        return {
            "estado": f["estado"],
            "progreso_actual": f["progreso_actual"],
            "progreso_total": f["progreso_total"],
            "error": f["error"],
        }

    @r.get("/temas/{tema_id}")
    def ver_tema(tema_id: int):
        t = con.execute("SELECT * FROM temas WHERE id=?", (tema_id,)).fetchone()
        if t is None:
            raise HTTPException(status_code=404, detail="Tema no encontrado")
        res = con.execute(
            "SELECT contenido_md FROM resumen WHERE tema_id=?", (tema_id,)
        ).fetchone()
        return {
            "id": t["id"],
            "titulo": t["titulo"],
            "resumen_md": res["contenido_md"] if res else "",
        }

    @r.delete("/temas/{tema_id}", status_code=204)
    def borrar_tema(tema_id: int):
        con.execute("DELETE FROM temas WHERE id=?", (tema_id,))
        con.commit()

    def _generar(tema_id: int, nivel: Nivel, faltan: int, job_id: int) -> None:
        con.execute("UPDATE jobs SET estado='en_curso' WHERE id=?", (job_id,))
        con.commit()
        try:
            generar(
                con,
                llm,
                settings.modelo_preguntas,
                tema_id,
                nivel,
                faltan,
                avance=lambda n: con.execute(
                    "UPDATE jobs SET progreso_actual=? WHERE id=?", (n, job_id)
                ),
            )
        except Exception as exc:
            con.execute(
                "UPDATE jobs SET estado='fallido', error=? WHERE id=?",
                (str(exc), job_id),
            )
        else:
            con.execute("UPDATE jobs SET estado='completado' WHERE id=?", (job_id,))
        con.commit()

    @r.post("/temas/{tema_id}/examenes")
    def iniciar_examen(tema_id: int, body: ExamenBody, fondo: BackgroundTasks):
        # Solo cuentan las no vistas: repetir preguntas ya respondidas no es
        # un examen, es memoria.
        sin_ver = con.execute(
            "SELECT COUNT(*) AS n FROM preguntas"
            " WHERE tema_id=? AND nivel=? AND veces_vista=0",
            (tema_id, body.nivel),
        ).fetchone()["n"]

        if sin_ver < body.cantidad:
            try:
                verificar_tope(con, settings.tope_gasto_mensual_usd)
            except TopeSuperado as exc:
                raise HTTPException(status_code=402, detail=str(exc)) from exc
            faltan = body.cantidad - sin_ver
            cur = con.execute(
                "INSERT INTO jobs (tema_id, tipo, estado, progreso_total)"
                " VALUES (?, 'generar_preguntas', 'pendiente', ?)",
                (tema_id, faltan),
            )
            job_id = int(cur.lastrowid)
            con.commit()
            fondo.add_task(_generar, tema_id, body.nivel, faltan, job_id)
            return {"job_id": job_id, "faltan": faltan}

        try:
            examen_id, preguntas = svc_examen.iniciar(
                con, tema_id, body.nivel, body.cantidad
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"examen_id": examen_id, "preguntas": preguntas}

    @r.get("/temas/{tema_id}/examenes")
    def historial(tema_id: int):
        filas = con.execute(
            "SELECT id, nivel, aciertos, total, terminado_en FROM examenes"
            " WHERE tema_id=? AND terminado_en IS NOT NULL"
            " ORDER BY terminado_en DESC LIMIT 20",
            (tema_id,),
        ).fetchall()
        return [dict(f) for f in filas]

    @r.post("/examenes/{examen_id}/respuestas")
    def responder(examen_id: int, body: RespuestaBody):
        try:
            return svc_examen.responder(
                con, examen_id, body.pregunta_id, body.elegida_idx
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @r.post("/examenes/{examen_id}/finalizar")
    def finalizar(examen_id: int):
        return svc_examen.finalizar(con, examen_id)

    @r.get("/gasto")
    def gasto():
        return {
            "mes_usd": round(gasto_del_mes(con), 4),
            "tope_usd": settings.tope_gasto_mensual_usd,
        }

    return r
