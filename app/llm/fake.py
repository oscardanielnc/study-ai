from app.llm.client import LLMError, LLMResult


class FakeLLMClient:
    """Doble determinista. Ningun test debe tocar la red."""

    def __init__(self, respuestas: list[str]):
        self._respuestas = list(respuestas)
        self.llamadas: list[dict] = []

    def completar(
        self,
        *,
        modelo: str,
        sistema: str,
        usuario: str,
        imagenes: list[bytes] | None = None,
        max_tokens: int = 8000,
        sin_razonamiento: bool = False,
    ) -> LLMResult:
        self.llamadas.append(
            {
                "modelo": modelo,
                "sistema": sistema,
                "usuario": usuario,
                "n_imagenes": len(imagenes or []),
            }
        )
        if not self._respuestas:
            raise LLMError("FakeLLMClient sin respuestas configuradas")
        texto = self._respuestas.pop(0)
        return LLMResult(
            texto=texto,
            tokens_in=max(1, len(sistema + usuario) // 4),
            tokens_out=max(1, len(texto) // 4),
            modelo=modelo,
        )
