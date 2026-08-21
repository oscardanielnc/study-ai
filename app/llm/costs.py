# USD por 1.000.000 de tokens: (entrada, salida). Fuente: spec §7, 2026-08-21.
PRECIOS: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-v4-pro": (0.435, 0.87),
    "deepseek/deepseek-v4-flash-vision-exp": (0.22, 0.66),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "anthropic/claude-sonnet-5": (2.00, 10.00),
}


def calcular(modelo: str, tokens_in: int, tokens_out: int) -> float:
    """Costo estimado en USD. Un modelo desconocido cuenta 0 en vez de romper."""
    precio_in, precio_out = PRECIOS.get(modelo, (0.0, 0.0))
    return (tokens_in * precio_in + tokens_out * precio_out) / 1_000_000
