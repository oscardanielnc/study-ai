from typing import Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Fallo al llamar al proveedor de IA."""


class LLMResult(BaseModel):
    texto: str
    tokens_in: int
    tokens_out: int
    modelo: str


class LLMClient(Protocol):
    def completar(
        self,
        *,
        modelo: str,
        sistema: str,
        usuario: str,
        imagenes: list[bytes] | None = None,
        max_tokens: int = 8000,
    ) -> LLMResult: ...
