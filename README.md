# Estudia

Convierte apuntes de clase (fotos de pizarra, manuscrito, PDFs) en resúmenes
estructurados y exámenes de opción múltiple en tres niveles.

**Producción:** https://study.oscarnavarro.dev (tras Cloudflare Access)

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

El frontend no tiene banco de pruebas. `node scripts/check_render.js` cubre lo
unico que ya fallo dos veces en silencio: el render de formulas y diagramas.

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

Proveedor: cualquier API con formato OpenAI (`LLM_BASE_URL`). Por defecto la de
DeepSeek directo, que evita el margen de OpenRouter.

| Paso | Modelo | Notas |
|---|---|---|
| Transcripción | `MODELO_TRANSCRIPCION` | Único paso con visión. Razonamiento **desactivado** |
| Resumen | `MODELO_RESUMEN` | DeepSeek V4 Pro |
| Preguntas | `MODELO_PREGUNTAS` | DeepSeek V4 Pro, solo al pedir el examen |

El examen se configura antes de generarlo: nivel y cantidad (10 a 40). Solo se
paga por las preguntas que faltan; las que quedaron sin ver se reutilizan. Cada
llamada produce como mucho 10 preguntas (una dificil ronda los 1.200 tokens de
salida, asi que un lote de 20 desbordaba `max_tokens`) y el conjunto se genera
en segundo plano con barra de progreso, porque el tunel corta a los 100 s.

El modelo de visión razona por defecto y es capaz de gastar los 8000 tokens
pensando, devolviendo texto vacío. Se le manda `thinking: disabled`: transcribir
es copiar, no razonar. Sale más completo, 2,6× más barato y 2,4× más rápido.
Una respuesta vacía es un error, nunca una fuente en blanco.

Medido sobre 5 fotos reales de apuntes densos: **$0,0148** el tema completo.

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

## Usuarios

Usuario y contraseña, nada más: sin correo, sin recuperación, sin perfiles.

- Las claves se guardan con `hashlib.scrypt` y sal por usuario. Es de la
  biblioteca estándar: no hay que compilar `bcrypt` en el ARM de la VM.
- Cada sesión es un token opaco en la tabla `sesiones`, que el móvil guarda en
  `localStorage` y **no caduca**. Volver a pedir la contraseña cada poco es lo
  que hace que la gente deje de abrir la app. Se revoca con "Salir", que borra
  la fila.
- Cada tema tiene dueño (`temas.usuario_id`) y todos los endpoints lo
  comprueban. Pedir el tema de otro devuelve **404, no 403**: quien no es el
  dueño no tiene por qué enterarse de que existe.
- `GET /api/yo` devuelve `null` en vez de 401, para que abrir la app sin
  sesión no parezca un error.
- El perfil (`PATCH /api/perfil`) cambia el nombre y la paleta; la
  contraseña va aparte (`POST /api/perfil/clave`) porque pide la de
  siempre y cierra las sesiones de los demás dispositivos.
- Las paletas (`papel`, `noche`, `bosque`, `atardecer`) se guardan en el
  usuario, no en el móvil, y se aplican desde `localStorage` antes de
  pedir nada al servidor para que no parpadee el tema por defecto.

La base que ya existía se migra en `db.py` con un `ALTER TABLE`: los temas
anteriores se quedan sin dueño y no los ve nadie.

## Despliegue

```bash
docker compose up -d --build
```

Escucha en `127.0.0.1:8083`. El hostname vive en `/etc/cloudflared/config.yml`
y el acceso lo controla una app de Cloudflare Access.

`~/backup-estudia.sh` en la VM copia la BD con la API `.backup` de SQLite
(no `cp`: con WAL activo eso captura estados a medias) y conserva 7 días.
Corre por cron a las 03:15 hora Lima.

## APK (Android)

El APK es un **TWA**: un envoltorio nativo que abre la misma web. No hay
código duplicado, así que un despliegue del servidor actualiza también la app
sin reinstalar nada. El trabajo pesado ya vive en el servidor, de modo que no
hace falta un servicio nativo en segundo plano.

`android/twa-manifest.json` es la fuente; el resto del proyecto Android lo
regenera Bubblewrap y no se versiona.

```bash
cd android
bubblewrap update --skipVersionUpgrade   # regenera desde twa-manifest.json
./gradlew.bat assembleRelease            # compila
powershell -ExecutionPolicy Bypass -File .\firmar.ps1   # firma -> estudia.apk
```

`static/.well-known/assetlinks.json` declara que el APK es dueño del dominio.
Sin ese archivo Android abre el TWA con la barra del navegador encima y deja
de parecer una app. La huella que contiene tiene que ser la de la clave que
firma el APK; `firmar.ps1` la imprime al terminar para poder compararla.

Comprobar que Google lo ve:

```bash
curl "https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://study.oscarnavarro.dev&relation=delegate_permission/common.handle_all_urls"
```

La clave de firma (`android/android.keystore`) no está en git a propósito:
quien la tenga puede publicar actualizaciones de la app. Si se pierde, Play
Store no admite más actualizaciones de ese paquete.
