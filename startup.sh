#!/bin/bash
# Startup command dla Azure App Service (Linux, Python) - ustaw w:
# Configuration -> General settings -> Startup Command: bash startup.sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn audytgmp.wsgi:application --bind=0.0.0.0:8000 --timeout 600
