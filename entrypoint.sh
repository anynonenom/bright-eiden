#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "Ensuring media directories exist..."
mkdir -p "${MEDIA_ROOT:-/app/media}/workspaces/icons"
chmod -R 777 "${MEDIA_ROOT:-/app/media}"
echo "Media root: ${MEDIA_ROOT:-/app/media}"
find "${MEDIA_ROOT:-/app/media}" -type f | head -20

echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating superuser if not exists..."
python manage.py createsuperuser --noinput || true

echo "Django MEDIA_ROOT:"
python -c "from django.conf import settings; print(settings.MEDIA_ROOT, settings.MEDIA_URL)"

echo "Starting gunicorn on port $PORT"
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:$PORT" \
    --workers 2 \
    --threads 2 \
    --timeout 120
