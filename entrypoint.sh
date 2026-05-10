#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "Ensuring media directories exist..."
mkdir -p "${MEDIA_ROOT:-/app/media}/workspaces/icons"
chmod -R 777 "${MEDIA_ROOT:-/app/media}"

echo "Running migrations..."
python manage.py migrate --noinput

if [ "${RESET_USERS}" = "1" ]; then
    echo "Resetting all users and organizations..."
    python manage.py reset_all_users
fi

if [ "${START_COMMAND}" = "worker" ]; then
    echo "Starting background task worker..."
    exec python manage.py process_tasks
else
    echo "Creating superuser if not exists..."
    python manage.py createsuperuser --noinput || true

    echo "Starting gunicorn on port $PORT"
    exec gunicorn config.wsgi:application \
        --bind "0.0.0.0:$PORT" \
        --workers 2 \
        --threads 2 \
        --timeout 120
fi
