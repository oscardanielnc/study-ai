from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

Nivel = Literal["facil", "intermedio", "dificil"]


class PreguntaGenerada(BaseModel):
    enunciado: str = Field(min_length=1)
    opciones: Annotated[list[str], Field(min_length=4, max_length=4)]
    correcta_idx: int = Field(ge=0, le=3)
    justificacion: str = Field(min_length=1)

    @field_validator("enunciado", "justificacion")
    @classmethod
    def no_solo_espacios(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("no puede estar vacio")
        return v.strip()


class LotePreguntas(BaseModel):
    preguntas: list[PreguntaGenerada]
