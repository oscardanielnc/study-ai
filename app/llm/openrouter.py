import base64

import httpx

from app.llm.client import LLMError, LLMResult

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """Cliente para cualquier API con formato OpenAI.

    Por defecto habla con OpenRouter, pero `base_url` permite apuntar al
    proveedor directo (p.ej. https://api.deepseek.com) y ahorrarse su margen.
    """

    def __init__(
        self,
        api_key: str,
        http: httpx.Client | None = None,
        base_url: str = BASE_URL,
        sin_razonamiento: bool = False,
    ):
        self._api_key = api_key
        self._http = http or httpx.Client(timeout=300.0)
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._sin_razonamiento = sin_razonamiento

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
        if sin_razonamiento or self._sin_razonamiento:
            # Transcribir no requiere razonar y el modelo de vision es capaz de
            # gastar el presupuesto entero pensando, dejando el texto vacio.
            payload["thinking"] = {"type": "disabled"}
        try:
            resp = self._http.post(
                self._url,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
            datos = resp.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"El proveedor de IA fallo: {exc}") from exc

        try:
            texto = datos["choices"][0]["message"]["content"]
            uso = datos.get("usage", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Respuesta inesperada del proveedor: {datos}") from exc

        if not (texto or "").strip():
            raise LLMError(
                "El modelo devolvio una respuesta vacia"
                f" (finish_reason={datos['choices'][0].get('finish_reason')})."
                " Suele ser que agoto max_tokens razonando."
            )

        return LLMResult(
            texto=texto,
            tokens_in=int(uso.get("prompt_tokens", 0)),
            tokens_out=int(uso.get("completion_tokens", 0)),
            modelo=modelo,
        )
