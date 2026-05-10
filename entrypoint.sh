#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "Ensuring media directory exists..."
mkdir -p "${MEDIA_ROOT:-/app/media}"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating superuser if not exists..."
python manage.py createsuperuser --noinput || true

echo "Starting gunicorn on port $PORT"
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:$PORT" \
    --workers 2 \
    --threads 2 \
    --timeout 120
