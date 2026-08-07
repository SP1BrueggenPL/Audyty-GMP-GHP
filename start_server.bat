@echo off
setlocal
cd /d "%~dp0"

echo === Audyty GMP/GHP - uruchamianie aplikacji ===

python --version >nul 2>&1
if errorlevel 1 (
    echo Nie znaleziono Pythona w PATH. Zainstaluj Python 3 i sprobuj ponownie.
    pause
    exit /b 1
)

echo Sprawdzanie / aktualizacja bazy danych...
python manage.py migrate
if errorlevel 1 (
    echo Migracja bazy danych nie powiodla sie.
    pause
    exit /b 1
)

echo Otwieranie przegladarki...
start "" "http://127.0.0.1:8000/"

echo Uruchamianie serwera (Ctrl+C aby zatrzymac)...
python manage.py runserver 127.0.0.1:8000

pause
