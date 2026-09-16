# 3.14, not 3.13 - the codebase uses syntax/semantics that only exist there
# (PEP 758 parenthesis-free multi-exception catches in scheduling/services.py;
# PEP 649 lazy annotation evaluation relied on in a couple of dataclasses).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBUG=False

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Explicit copies only - never `COPY . .`, so local secrets (.env,
# *-service-account.json, client_secret*.json, token.json, db.sqlite3) can
# never end up in an image layer even if .dockerignore is out of date.
COPY manage.py .
COPY config/ config/
COPY scheduling/ scheduling/
COPY static/ static/
COPY entrypoint.sh .

RUN python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 appuser \
    && chmod +x entrypoint.sh \
    && mkdir -p /app/run \
    && chown -R appuser:appuser /app

# Stays root here so entrypoint.sh can chown a freshly-mounted volume (Backyard's
# PVC mounts root-owned) before it drops to appuser to run migrate/gunicorn -
# the app process itself never runs as root.
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
