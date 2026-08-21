import base64

import httpx

from app.llm.client import LLMError, LLMResult

URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient:
    """Cliente de OpenRouter. La API es compatible con el formato de OpenAI."""

    def __init__(self, api_key: str, http: httpx.Client | None = None):
        self._api_key = api_key
        self._http = http or httpx.Client(timeout=180.0)

    def completar(
        self,
        *,
        modelo: str,
        sistema: str,
        usuario: str,
        imagenes: list[bytes] | None = None,
        max_tokens: int = 8000,
    ) -> LLMResult:
        # Las imagenes van ANTES del texto y el texto variable al final:
        # asi el prefijo estable se puede cachear entre llamadas.
        partes: list[dict] = []
        for img in imagenes or []:
            b64 = base64.b64encode(img).decode()
            partes.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
        partes.append({"type": "text", "text": usuario})

        payload = {
            "model": modelo,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": partes},
            ],
        }
        try:
            resp = self._http.post(
                URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
            datos = resp.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenRouter fallo: {exc}") from exc

        try:
            texto = datos["choices"][0]["message"]["content"]
            uso = datos.get("usage", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Respuesta inesperada de OpenRouter: {datos}") from exc

        return LLMResult(
            texto=texto,
            tokens_in=int(uso.get("prompt_tokens", 0)),
            tokens_out=int(uso.get("completion_tokens", 0)),
            modelo=modelo,
        )
