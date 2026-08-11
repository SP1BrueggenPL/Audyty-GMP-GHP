# Audyty GMP/GHP — baza aplikacji (Django)

Cyfrowa wersja procesu inspekcji GMP/GHP (WCE/WPP, WLS, WED) opisanego w
`Wytyczne/Process.docx`: checklisty (edytowalne w samej aplikacji), automatyczne
tworzenie wpisów w rejestrze niezgodności, dwuetapowy formularz (audytor /
osoba odpowiedzialna za obszar), raport z inspekcji do wysyłki e-mail,
przypomnienia/eskalacje, role i uprawnienia per dział, podpowiedzi AI oraz
wielozakładkowe dashboardy raportowe.

## Uruchomienie lokalne

Dwuklik na `start_server.bat` (uruchamia migracje i serwer, otwiera przeglądarkę),
albo ręcznie:

```bash
cd webapp
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata checklists          # struktura checklist WCE/WPP, WLS, WED
python manage.py seed_demo_data               # konta testowe (patrz niżej)
python manage.py runserver
```

Otwórz `http://127.0.0.1:8000`.

## Logowanie

**Dwuetapowo: numer chipa (5 cyfr) + 6-znakowy kod autoryzujący.**
Pierwsze logowanie na danym chipie (albo zaraz po resecie kodu przez admina) -
system prosi o ustawienie własnego kodu (dwa razy, dla potwierdzenia). Od tego
momentu każde kolejne logowanie to: numer chipa -> ten sam kod. Kod jest
przechowywany tak samo bezpiecznie jak zwykłe hasło Django (hashowany, admin
nigdy go nie widzi - może go tylko zresetować).

Konta pracownicze tworzy się w zakładce **Użytkownicy** (widoczna dla ról
QualityAdmin i Helpdesk) — login to zawsze 5-cyfrowy numer, walidowany przy
zapisie. Tam samo można **zresetować komuś kod** (przycisk „🔑 Resetuj kod” -
w liście albo na stronie edycji), np. gdy ktoś go zapomni - przy następnym
logowaniu ta osoba ustawi nowy.

Wyjątek: konto **admina** (superużytkownik) loguje się login+hasło pod
`/login/` i zarządza samo sobą / innymi kontami administratorskimi w panelu
Django `/admin/` — te konta są celowo wyłączone z zakładki „Użytkownicy”,
żeby administrator nie mógł sam sobie przez przypadek usunąć hasła.

Konta testowe (`seed_demo_data`):
- `admin` / `ZmieńTeHasło123!` — administrator (panel `/admin/` + `/login/`)
- `21012`, `10001`–`10013` — Audytorzy
- `10020` — Helpdesk
- `10031`–`10034` — Pakownia/Produkcja (zmiany D/D/D/A)
- `10035` — Logistyka (zmiana C)
- `10036` — Techniczny (bez zmiany - pracownik niezmianowy)

**Tylko dev** — do zmiany/usunięcia przed jakimkolwiek wdrożeniem.

## Role i uprawnienia

| Rola | Widzi niezgodności/raporty | Przeprowadza inspekcje | Zakładka Raporty | Zarządza użytkownikami | Panel Django `/admin/` |
|---|---|---|---|---|---|
| QualityAdmin | wszystko | tak | tak | tak | nie |
| Helpdesk | wszystko | tak | tak | tak | tak |
| Audytor | wszystko | tak | nie | nie | nie |
| Pakownia / Produkcja | WCE, WPP, MIX-Konfekcjonowanie | nie | nie | nie | nie |
| Techniczny | WED | nie | nie | nie | nie |
| Logistyka | WLS | nie | nie | nie | nie |

QualityAdmin i Helpdesk mają identyczne uprawnienia **w samej aplikacji**
(Użytkownicy, edytor checklisty, edycja/usuwanie inspekcji i niezgodności,
Raporty) - różnica jest tylko taka, że Helpdesk dodatkowo ma dostęp do
surowego panelu Django `/admin/` (do wsparcia technicznego/naprawy danych),
a QualityAdmin nie.

Role, dział i zmianę przypisuje administrator w zakładce **Użytkownicy**.
Pole **zmiana** jest nieobowiązkowe — zostaw puste dla osób niezmianowych.

## Edycja treści checklisty (w aplikacji, nie w Django admin)

Role QualityAdmin i Helpdesk widzą przycisk **„✎ Edytuj treść checklisty”** przy każdym
szablonie (panel główny i „Nowa inspekcja”). Trzypoziomowy edytor:
szablon → sekcje (zakresy wymagań, max punktów) → podsekcje → punkty
kontrolne. Dodawanie/usuwanie wierszy działa przez przyciski „+ Dodaj…” i
checkbox „Usuń” — bez wchodzenia do `/admin/`.

## Jak liczone są punkty

- Każda niezgodność przypisana do konkretnego punktu checklisty odlicza
  **1 punkt** od sekcji, do której ten punkt należy (minimum 0 — jeśli liczba
  niezgodności w sekcji ≥ max punktów, sekcja ma 0). Liczone automatycznie.
- Każda **dodatkowa niezgodność** (przycisk „+ Dodaj dodatkową niezgodność”,
  niezwiązana z konkretnym zaznaczeniem punktu) odlicza **1 punkt od
  ogólnego wyniku inspekcji**, a nie z konkretnej sekcji.
- Wynik jest liczony raz, w momencie zapisu inspekcji (nie przelicza się
  wstecz, jeśli ktoś później edytuje niezgodność).

## Przedstawiciele obszaru i osoba odpowiedzialna

Audytorem jest zawsze zalogowana osoba (bez wyboru z listy). Po wybraniu
zmiany w formularzu inspekcji, system automatycznie pobiera (AJAX,
`/api/osoby-ze-zmiany/`) wszystkie osoby z tą zmianą i pokazuje je jako
zaznaczone checkboxy — można odznaczyć kogoś, kto nie brał udziału. Przy
zaznaczeniu punktu jako niezgodność, pole „osoba odpowiedzialna” pokazuje
tylko te osoby (bez ponownego wybierania z całej listy pracowników).

> Formularz „Dodaj niezgodność” poza pełną inspekcją (ad-hoc) nie ma jeszcze
> tej automatyzacji — osobę odpowiedzialną wybiera się tam manualnie.

## Podpowiedzi AI (Azure OpenAI, GPT-4o)

Przy zdjęciu niezgodności jest przycisk „✨ Podpowiedz opis (AI)” — wysyła
zdjęcie + ostatnie opisy niezgodności dla tego samego punktu checklisty do
Azure OpenAI i wstawia zaproponowany opis (do edycji przez audytora, nie
automatycznie). Wymaga zmiennych środowiskowych:

```
AZURE_OPENAI_ENDPOINT=https://<twoj-zasob>.openai.azure.com/
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-08-01-preview
```

Bez tych zmiennych funkcja jest po prostu nieaktywna (komunikat w UI) —
reszta aplikacji działa normalnie. Logika w `audits/ai.py`.

## Raporty (`/raporty/`, tylko QualityAdmin/Helpdesk)

Cztery zakładki, odpowiadające zakładkom z arkusza
`2026_NIEZGODNOŚCI GMP_GHP_2026_Q1 2026.xlsx`, z filtrem działu i roku:

1. **Przegląd** — KPI, wykresy (status, dział, top 10 kategorii, trend
   miesięczny, średni wynik inspekcji).
2. **Wyniki inspekcji** — średni wynik [%] wg działu/zmiany/miesiąca + roczna
   średnia (odpowiednik arkusza `WYNIKI_2026`, górna tabela) oraz liczba
   niezgodności wg kwartału z porównaniem lat (dolna tabela tego arkusza).
3. **Niezgodności wg grup** — liczba NC wg kategorii GMP/GHP w podziale na
   kwartały, z udziałem % (odpowiednik `Q1 NC wg grup` / `*_grupy_NC`).
4. **Niezgodności wg punktów** — ranking konkretnych punktów checklisty w
   ramach każdej kategorii, w podziale na kwartały (odpowiednik `*_typy_NC` /
   „podsumowanie kwartalne”).

Wykresy renderowane przez Chart.js z CDN (jsdelivr) — jeśli środowisko
produkcyjne nie ma dostępu do internetu, trzeba pobrać plik lokalnie do
`static/js/`.

**Kolorowanie wyników** w zakładce „Wyniki inspekcji” (odpowiednik warunkowego
formatowania w Excelu): ≥85% — niebieski (dobry wynik), 70–84% — żółty (do
obserwacji), <70% — czerwony (wymaga uwagi). Legenda nad tabelą.

**Eksport do Excela** — przycisk „⬇ Eksportuj do Excela” generuje jeden plik
`.xlsx` z czterema zakładkami (Przegląd, Wyniki inspekcji, NC wg grup, NC wg
punktów) dla aktualnie wybranego działu/roku, z tym samym kolorowaniem
wyników co na ekranie. Logika w `audits/reports_export.py`.

## Panel Django `/admin/` — tylko dla roli Helpdesk

Rola **QualityAdmin** ma te same uprawnienia w aplikacji co Helpdesk
(Użytkownicy, edytor checklisty, Raporty, edycja/usuwanie inspekcji i
niezgodności), ale **nie ma** dostępu do surowego panelu Django — link
„Admin” w górnym menu i dostęp do `/admin/` mają tylko konta z rolą
**Helpdesk** (oraz superużytkownik `admin`, do wsparcia technicznego/naprawy
danych). To ustawiane automatycznie w `User.save()` (`accounts/models.py`) —
zmiana roli na Helpdesk włącza `is_staff`, każda inna rola (poza superuserem)
je wyłącza.

## Wdrożenie: GitHub -> Azure App Service

Repozytorium: https://github.com/SP1BrueggenPL/Audyty-GMP-GHP (root repo =
zawartość tego folderu `webapp/` — folder `Wytyczne/` z oryginalnymi danymi
audytowymi **nie** jest i nie powinien być w repo, zawiera realne dane firmy).

Wdrożenie do App Service `AuditGMPGHP` jest zautomatyzowane przez GitHub
Actions (`.github/workflows/main_auditgmpghp.yml`, wygenerowane przez Azure
Deployment Center) — każdy `push` do `main` buduje i wdraża aplikację
automatycznie. Poniższe punkty to jednorazowa konfiguracja środowiska
(zmienne, baza danych), nie kroki do powtarzania przy każdym wdrożeniu.

**1. Zmienne środowiskowe** w Azure App Service (Configuration -> Environment
variables) — patrz `.env.example`:

| Zmienna | Wartość |
|---|---|
| `SECRET_KEY` | długi losowy ciąg (np. `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DEBUG` | `False` |
| `DATABASE_URL` | connection string do PostgreSQL na Azure (patrz niżej) |
| `AZURE_OPENAI_ENDPOINT` | endpoint zasobu Azure OpenAI |
| `AZURE_OPENAI_KEY` | klucz zasobu Azure OpenAI |
| `AZURE_OPENAI_DEPLOYMENT` | nazwa wdrożenia modelu, np. `gpt-4o` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` (Oryz uruchomi `pip install -r requirements.txt`) |

`WEBSITE_HOSTNAME` (adres `*.azurewebsites.net`) jest ustawiane przez Azure
automatycznie i dodawane do `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` w kodzie —
nie trzeba go dodawać ręcznie.

**2. Baza danych** — Azure Database for PostgreSQL, `DATABASE_URL` w formacie:
```
postgres://uzytkownik:haslo@nazwa-serwera.postgres.database.azure.com:5432/nazwa_bazy?sslmode=require
```
Bez tej zmiennej aplikacja lokalnie dalej używa SQLite (`dj-database-url`,
`audytgmp/settings.py`).

**3. Startup Command** w Azure (Configuration -> General settings):
```
bash startup.sh
```
Skrypt (`startup.sh`) uruchamia migracje, `collectstatic` (statyki serwowane
przez whitenoise — nie trzeba osobnego CDN/Blob Storage) i `gunicorn`.

**4. Pierwsze uruchomienie na nowej bazie** (raz, przez konsolę SSH/Kudu w
Azure App Service albo lokalnie z tym samym `DATABASE_URL`):
```bash
python manage.py migrate
python manage.py loaddata checklists
python manage.py create_admin_chip 21012 --imie Jan --nazwisko Kowalski  # pierwsze konto z rolą QualityAdmin - kod ustawisz przy pierwszym logowaniu
python manage.py createsuperuser  # opcjonalnie: konto do panelu /admin/ i /login/ (login+hasło)
```

**5. Media (zdjęcia niezgodności)** — na Azure App Service (Linux) trzymane w
`/home/media` (jedyny trwały katalog, przetrwa restart/redeploy). To
rozwiązanie tymczasowe/na start; docelowo warto przenieść na Azure Blob
Storage (`django-storages`) dla trwałości przy skalowaniu do wielu instancji.

**6. Bezpieczeństwo produkcyjne** — przy `DEBUG=False` automatycznie
włączane jest: przekierowanie na HTTPS, bezpieczne ciasteczka sesji/CSRF,
HSTS (`audytgmp/settings.py`, sekcja na końcu pliku).

## Inne

- `send_nc_reminders` (management command) — przypomnienia do osoby
  odpowiedzialnej po 7 dniach, eskalacja po 14 dniach (`NC_REMINDER_AFTER_DAYS`
  / `NC_ESCALATION_AFTER_DAYS` w `settings.py`). Do harmonogramu Windows/cron.
- Jeśli treść checklist w plikach `Wytyczne/Templatki/*.xlsx` się zmieni,
  zamiast edytora w aplikacji można też uruchomić ponownie:
  `python manage.py import_checklists_from_xlsx` (nadpisuje cały szablon).

## Design / branding

Kolory i typografia zgodne z Corporate Design Brüggen: Coral Red `#FF4143`,
Deep Claret `#661C31`, Golden Yellow `#E2BC54` (tylko akcent), Dusky Pink,
Steel Blue, Charcoal. Nagłówki: Franklin Gothic Demi, tekst: Franklin Gothic
Book, bez kursywy. Zmienne kolorów w `static/css/brand.css` (`:root`).

## Rzeczy do dopracowania w kolejnej iteracji

1. Automatyczny dobór osoby odpowiedzialnej wg zmiany w formularzu „Dodaj
   niezgodność” (ad-hoc, poza pełną inspekcją).
2. **Powiadomienia** — `EMAIL_BACKEND` jest ustawiony na konsolę (dev).
   Przed wdrożeniem podłączyć prawdziwy serwer SMTP Brüggen.
3. **Fizyczna integracja czytnika chipów** — pole numeru to zwykłe pole
   tekstowe; podłączenie prawdziwego czytnika RFID/USB wymaga testów na
   docelowym sprzęcie (czytniki HID zwykle "wpisują" numer + Enter, co
   powinno działać od razu dla pierwszego kroku). Kod autoryzujący (krok 2)
   i tak trzeba wpisać ręcznie z klawiatury/ekranu dotykowego.
4. **Media na Azure Blob Storage** — obecnie zdjęcia trzymane są na dysku
   `/home/media` App Service; przy większej skali warto przejść na
   `django-storages` + Blob Storage.
5. **Chart.js z CDN** — do zweryfikowania w środowisku produkcyjnym/intranet
   (jeśli Azure App Service ma ograniczony dostęp wychodzący do internetu).
