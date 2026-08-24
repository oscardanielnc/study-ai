FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/estudia.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

# Sin root: si alguien logra ejecutar algo dentro del contenedor, que no sea
# como administrador. /data es un volumen, asi que hay que darselo antes de
# bajar de privilegios.
RUN useradd --system --uid 10001 estudia \
    && mkdir -p /data \
    && chown -R estudia:estudia /data /srv
USER estudia

VOLUME /data
EXPOSE 8000
# 1 worker: la VM tiene 1 vCPU y SQLite no gana nada con mas.
CMD ["uvicorn", "app.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
