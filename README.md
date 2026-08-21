# Estudia

Convierte apuntes de clase (fotos de pizarra, manuscrito, PDFs) en resúmenes
estructurados y exámenes de opción múltiple en tres niveles.

**Producción:** https://estudia.oscarnavarro.dev (tras Cloudflare Access)

## Desarrollo

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux: .venv/bin/python
cp .env.example .env          # poner la key de OpenRouter
.venv/Scripts/python -m pytest
.venv/Scripts/python -m uvicorn app.main:app --factory --reload --port 8083
```

## Tests

`pytest` **no toca la red**: toda la IA pasa por `FakeLLMClient`. La suite corre
offline, gratis y en segundos.

El test de contrato hace llamadas reales y está excluido por defecto. Ejecútalo
al cambiar de modelo:

```bash
pytest -m contrato -v
```

## Arquitectura

```
Cloudflare Access -> Cloudflare Tunnel -> 127.0.0.1:8083 -> contenedor "estudia"
                                                            |-- FastAPI + uvicorn
                                                            |-- static/ (PWA)
                                                            +-- /data/estudia.db
```

Un solo usuario, SQLite en modo WAL, sin Postgres ni Redis. El procesamiento va
en `BackgroundTasks` con polling porque el túnel corta las peticiones HTTP a los
100 s.

## Pipeline de IA

| Paso | Modelo | Notas |
|---|---|---|
| Transcripción | `MODELO_TRANSCRIPCION` | Único paso que necesita visión |
| Resumen | `MODELO_RESUMEN` | DeepSeek V4 Pro |
| Preguntas | `MODELO_PREGUNTAS` | DeepSeek V4 Pro, lote de 20, perezoso |

Ahorros aplicados: los PDFs digitales se extraen con `pypdf` (cero tokens), las
imágenes se reescalan a 1100 px antes de enviarlas, y las llamadas derivadas
comparten prefijo cacheable.

**Las imágenes originales se borran** en cuanto su transcripción está en la BD.
Por eso el prompt exige marcar lo ilegible con `[?]` en vez de adivinar: un dato
inventado sería indetectable.

## Spike de modelo de visión

```bash
python scripts/spike_vision.py ruta/a/fotos
```

Compara los candidatos sobre material real y escribe `spike-resultados/`.

## Despliegue

```bash
docker compose up -d --build
```

Escucha en `127.0.0.1:8083`. El hostname vive en `/etc/cloudflared/config.yml`.
