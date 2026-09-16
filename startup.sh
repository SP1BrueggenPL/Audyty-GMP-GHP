#!/bin/bash
# Startup command dla Azure App Service (Linux, Python) - ustaw w:
# Configuration -> General settings -> Startup Command: bash startup.sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
# --workers 2: jeden worker (poprzednie ustawienie) oznaczał, że KAŻDE żądanie
# (nawet krótkie wywołanie AI/maila w tle) blokowało całą aplikację dla
# wszystkich innych użytkowników na czas jego trwania. Dwa workery ograniczają
# ten problem (drugi request wciąż jest obsługiwany), bez większego obciążenia
# pamięci - w razie potrzeby zwiększ, jeśli plan Azure App Service ma na to
# zasób (RAM).
# --timeout 120: skrócone z 600s - wywołania AI/e-mail mają teraz własne,
# krótsze limity czasu (patrz audits/ai.py, audits/email_acs.py), więc
# request nie powinien trwać dłużej niż ok. minutę w normalnych warunkach;
# 120s to bufor bezpieczeństwa, nie główny mechanizm ochronny.
gunicorn audytgmp.wsgi:application --bind=0.0.0.0:8000 --workers 2 --timeout 120
