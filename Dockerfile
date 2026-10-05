# Imagen base fijada por digest: una etiqueta se puede mover, un digest no.
# Para actualizarla, consulta el digest nuevo de python:3.12-slim y cámbialo aquí, en un commit propio.
FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

# El digest fija la base; las actualizaciones de seguridad de Debian se aplican al construir.
# Sin esto, Trivy bloqueó la imagen por CVE-2026-103111 (libpcre2-8-0, arreglada en 10.46-1~deb13u3).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Solo se instala lo que está en el lock, y solo si cada archivo coincide con su hash.
COPY requirements.lock .
RUN pip install --require-hashes -r requirements.lock

# El código queda de root y solo legible para la app: el proceso no puede modificarse a sí mismo.
COPY app ./app
RUN useradd --no-create-home --shell /usr/sbin/nologin --uid 1001 oraculo
USER oraculo

EXPOSE 8080
# La misma imagen sirve la API (por defecto) y los nodos reales (APP_MODULE=app.node:app).
# Solo esos dos módulos: una variable de entorno no puede convertir la imagen en otra cosa.
CMD case "${APP_MODULE:=app.main:app}" in app.main:app|app.node:app) ;; *) echo "APP_MODULE no permitido" >&2; exit 1 ;; esac; \
    exec uvicorn "$APP_MODULE" --host 0.0.0.0 --port "${PORT}"
