import sqlite3

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm.client import LLMClient
from app.llm.contabilidad import TopeSuperado, gasto_del_mes, verificar_tope
from app.models import Nivel
from app.services import auth
from app.services import examen as svc_examen
from app.services.ingesta import Archivo, crear_job, procesar
from app.services.preguntas import LOTE_MAX, generar

CANTIDADES = (10, 20, 30, 40)


class NivelBody(BaseModel):
    nivel: Nivel


class Credenciales(BaseModel):
    usuario: str
    clave: str


class PerfilBody(BaseModel):
    usuario: str | None = None
    tema_visual: str | None = None


class ClaveBody(BaseModel):
    actual: str
    nueva: str


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

    def _token(authorization: str | None = Header(default=None)) -> str:
        cabecera = authorization or ""
        return cabecera[7:].strip() if cabecera.startswith("Bearer ") else ""

    def _quien(token: str = Depends(_token)) -> int:
        """La sesion de quien llama. Sin ella no se ve ni se toca nada."""
        fila = auth.usuario_de_token(con, token)
        if fila is None:
            raise HTTPException(status_code=401, detail="Sesion no valida")
        return int(fila["id"])

    def _mio(tema_id: int, yo: int) -> None:
        """404 y no 403: quien no es el dueno no tiene por que enterarse de
        que el tema existe."""
        if (
            con.execute(
                "SELECT 1 FROM temas WHERE id=? AND usuario_id=?", (tema_id, yo)
            ).fetchone()
            is None
        ):
            raise HTTPException(status_code=404, detail="Tema no encontrado")

    def _mi_examen(examen_id: int, yo: int) -> None:
        if (
            con.execute(
                "SELECT 1 FROM examenes e JOIN temas t ON t.id=e.tema_id"
                " WHERE e.id=? AND t.usuario_id=?",
                (examen_id, yo),
            ).fetchone()
            is None
        ):
            raise HTTPException(status_code=404, detail="Examen no encontrado")

    def _sesion_nueva(token: str, usuario: str) -> dict:
        fila = con.execute(
            "SELECT tema_visual FROM usuarios WHERE usuario=?", (usuario,)
        ).fetchone()
        return {"token": token, "usuario": usuario, "tema_visual": fila["tema_visual"]}

    @r.post("/registro")
    def registro(body: Credenciales):
        try:
            token = auth.registrar(con, body.usuario, body.clave)
        except auth.DatosInvalidos as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except auth.UsuarioOcupado as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _sesion_nueva(token, body.usuario)

    @r.post("/login")
    def login(body: Credenciales):
        try:
            token = auth.entrar(con, body.usuario, body.clave)
        except auth.CredencialesMalas as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return _sesion_nueva(token, body.usuario)

    @r.get("/yo")
    def yo_soy(token: str = Depends(_token)):
        """Quien soy segun el token guardado en el movil. Devuelve null en vez
        de 401 para que la pantalla de entrada no parezca un error."""
        fila = auth.usuario_de_token(con, token)
        if fila is None:
            return None
        return {"usuario": fila["usuario"], "tema_visual": fila["tema_visual"]}

    @r.patch("/perfil")
    def editar_perfil(body: PerfilBody, yo: int = Depends(_quien)):
        """Nombre y tema visual. La clave va aparte porque pide la de siempre."""
        try:
            if body.usuario is not None:
                auth.cambiar_usuario(con, yo, body.usuario.strip())
            if body.tema_visual is not None:
                auth.cambiar_tema(con, yo, body.tema_visual)
        except auth.DatosInvalidos as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except auth.UsuarioOcupado as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        fila = con.execute(
            "SELECT usuario, tema_visual FROM usuarios WHERE id=?", (yo,)
        ).fetchone()
        return {"usuario": fila["usuario"], "tema_visual": fila["tema_visual"]}

    @r.post("/perfil/clave", status_code=204)
    def cambiar_la_clave(
        body: ClaveBody, yo: int = Depends(_quien), token: str = Depends(_token)
    ):
        try:
            auth.cambiar_clave(con, yo, body.actual, body.nueva)
        except auth.CredencialesMalas as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except auth.DatosInvalidos as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # La sesion de aqui se conserva: cambiar la clave no puede echarte del
        # movil en el que la acabas de cambiar.
        auth.cerrar_otras_sesiones(con, yo, token)

    @r.post("/salir", status_code=204)
    def cerrar(token: str = Depends(_token)):
        auth.salir(con, token)

    async def _leer(archivos: list[UploadFile]) -> list[Archivo]:
        return [Archivo(a.filename or "sin-nombre", await a.read()) for a in archivos]

    @r.get("/temas")
    def listar_temas(yo: int = Depends(_quien)):
        filas = con.execute(
            "SELECT t.id, t.titulo, t.actualizado_en,"
            " (SELECT COUNT(*) FROM fuentes f WHERE f.tema_id=t.id) AS n_fuentes"
            " FROM temas t WHERE t.usuario_id=? ORDER BY t.actualizado_en DESC",
            (yo,),
        ).fetchall()
        return [dict(f) for f in filas]

    @r.post("/temas")
    async def crear_tema(
        fondo: BackgroundTasks,
        archivos: list[UploadFile],
        yo: int = Depends(_quien),
    ):
        try:
            verificar_tope(con, settings.tope_gasto_mensual_usd)
        except TopeSuperado as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc

        # El tema se crea DESPUES de tener los bytes: si la subida se corta a
        # medias no queda una tarjeta 'Procesando...' eterna en la lista.
        datos = await _leer(archivos)
        cur = con.execute(
            "INSERT INTO temas (usuario_id, titulo) VALUES (?, 'Procesando...')",
            (yo,),
        )
        tema_id = int(cur.lastrowid)
        con.commit()
        job_id = crear_job(con, tema_id, len(datos))
        fondo.add_task(procesar, con, llm, settings, tema_id, job_id, datos)
        return {"tema_id": tema_id, "job_id": job_id}

    @r.get("/jobs/{job_id}")
    def ver_job(job_id: int, yo: int = Depends(_quien)):
        f = con.execute(
            "SELECT j.* FROM jobs j JOIN temas t ON t.id=j.tema_id"
            " WHERE j.id=? AND t.usuario_id=?",
            (job_id, yo),
        ).fetchone()
        if f is None:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        return {
            "estado": f["estado"],
            "progreso_actual": f["progreso_actual"],
            "progreso_total": f["progreso_total"],
            "error": f["error"],
        }

    @r.get("/temas/{tema_id}/job")
    def ultimo_job(tema_id: int, yo: int = Depends(_quien)):
        """El job vivo de un tema. Permite reengancharse a un proceso en curso
        tras recargar o tras que el movil descarte la pestana."""
        _mio(tema_id, yo)
        f = con.execute(
            "SELECT * FROM jobs WHERE tema_id=? ORDER BY id DESC LIMIT 1",
            (tema_id,),
        ).fetchone()
        if f is None:
            return None
        return {
            "id": f["id"],
            "tipo": f["tipo"],
            "estado": f["estado"],
            "progreso_actual": f["progreso_actual"],
            "progreso_total": f["progreso_total"],
            "error": f["error"],
        }

    @r.get("/temas/{tema_id}")
    def ver_tema(tema_id: int, yo: int = Depends(_quien)):
        t = con.execute(
            "SELECT * FROM temas WHERE id=? AND usuario_id=?", (tema_id, yo)
        ).fetchone()
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
    def borrar_tema(tema_id: int, yo: int = Depends(_quien)):
        con.execute("DELETE FROM temas WHERE id=? AND usuario_id=?", (tema_id, yo))
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
            con.execute(
                "UPDATE jobs SET estado='completado',"
                " progreso_actual=progreso_total WHERE id=?",
                (job_id,),
            )
        con.commit()

    @r.post("/temas/{tema_id}/examenes")
    def iniciar_examen(
        tema_id: int,
        body: ExamenBody,
        fondo: BackgroundTasks,
        yo: int = Depends(_quien),
    ):
        _mio(tema_id, yo)
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
    def historial(tema_id: int, yo: int = Depends(_quien)):
        _mio(tema_id, yo)
        filas = con.execute(
            "SELECT id, nivel, aciertos, total, terminado_en FROM examenes"
            " WHERE tema_id=? AND terminado_en IS NOT NULL"
            " ORDER BY terminado_en DESC LIMIT 20",
            (tema_id,),
        ).fetchall()
        return [dict(f) for f in filas]

    @r.post("/examenes/{examen_id}/respuestas")
    def responder(examen_id: int, body: RespuestaBody, yo: int = Depends(_quien)):
        _mi_examen(examen_id, yo)
        try:
            return svc_examen.responder(
                con, examen_id, body.pregunta_id, body.elegida_idx
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @r.post("/examenes/{examen_id}/finalizar")
    def finalizar(examen_id: int, yo: int = Depends(_quien)):
        _mi_examen(examen_id, yo)
        return svc_examen.finalizar(con, examen_id)

    @r.get("/gasto")
    def gasto(yo: int = Depends(_quien)):
        return {
            "mes_usd": round(gasto_del_mes(con), 4),
            "tope_usd": settings.tope_gasto_mensual_usd,
        }

    return r
