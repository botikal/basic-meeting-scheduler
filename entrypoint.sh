#!/bin/sh
# Runs as root (see Dockerfile) only to fix ownership of mounted volumes -
# Backyard's persistent-storage PVC mounts root-owned regardless of what the
# image set at build time - then drops to appuser for the app itself, which
# never runs as root.
set -eu

if [ -n "${GOOGLE_TOKEN_JSON:-}" ] && [ -n "${GOOGLE_TOKEN_FILE:-}" ]; then
    mkdir -p "$(dirname "$GOOGLE_TOKEN_FILE")"
    printf '%s' "$GOOGLE_TOKEN_JSON" > "$GOOGLE_TOKEN_FILE"
fi

chown -R appuser:appuser /app/run
[ -d /data ] && chown -R appuser:appuser /data

exec su appuser -s /bin/sh -c '
    set -eu
    python manage.py migrate --noinput
    python manage.py ensure_admin
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
'
