"""
Podpowiedzi opisu niezgodności na bazie zdjęcia (Azure OpenAI, model GPT-4o).

Wymaga skonfigurowania zmiennych środowiskowych (patrz settings.py):
    AZURE_OPENAI_ENDPOINT      - np. https://<twoj-zasob>.openai.azure.com/
    AZURE_OPENAI_KEY       - klucz zasobu Azure OpenAI
    AZURE_OPENAI_DEPLOYMENT    - nazwa wdrożenia modelu (np. "gpt-4o")
    AZURE_OPENAI_API_VERSION   - domyślnie "2024-08-01-preview"

Jeśli te wartości nie są ustawione, funkcja zwraca available=False i UI
po prostu nie pokazuje podpowiedzi - reszta aplikacji działa normalnie.
"""
import base64
import re

from django.conf import settings

try:
    from openai import AzureOpenAI
except ImportError:  # pragma: no cover
    AzureOpenAI = None

# Domyślny timeout klienta openai to 600s - dokładnie tyle, ile wynosi limit
# gunicorna (--timeout 600 w startup.sh). Gdy Azure OpenAI zwalnia/wisi, oba
# limity trafiają niemal jednocześnie i gunicorn zabija JEDYNEGO workera,
# przez co CAŁA aplikacja jest niedostępna aż do restartu. Krótszy, jawny
# timeout sprawia, że nieudane zapytanie AI kończy się czytelnym błędem
# zamiast wywalać cały serwer.
REQUEST_TIMEOUT_SECONDS = 45.0

PROMPT_TEMPLATE = """Jesteś asystentem audytora GMP/GHP w zakładzie produkcji spożywczej.
Audytor jest właśnie przy tym punkcie checklisty:
Sekcja: {section_name}
Podsekcja: {subsection_name}
Punkt {item_number}: {item_description}

Zadanie:
1. Oceń, czy to, co widać na zdjęciu, tematycznie pasuje do TEGO punktu checklisty powyżej.
2. Jeśli PASUJE: zaproponuj krótki, konkretny opis niezgodności (1-3 zdania po polsku, w stylu
   audytowym: co i gdzie jest niezgodne). Nie wymyślaj lokalizacji, których nie widać na zdjęciu -
   jeśli nie jesteś w stanie jej określić, opisz tylko charakter niezgodności.
3. Jeśli NIE PASUJE (zdjęcie wyraźnie dotyczy innego tematu niż ten punkt) - i tak zaproponuj
   opis tego, co widać, ale DODATKOWO w polu NIEDOPASOWANIE wskaż najlepiej pasujący punkt
   z pełnej listy checklisty poniżej (podaj DOKŁADNIE jego numer z listy) i krótko uzasadnij.
   Jeśli aktualny punkt pasuje najlepiej, wpisz "brak".

Pełna lista punktów checklisty (numer - sekcja - treść) - użyj WYŁĄCZNIE do wskazania numeru
przy niedopasowaniu, nie cytuj jej w opisie:
{all_points}

Przykłady wcześniejszych opisów niezgodności dla TEGO punktu (dla stylu/kontekstu, nie
kopiuj ich treści dosłownie):
{examples}

Odpowiedz WYŁĄCZNIE w formacie:
OPIS: <opis niezgodności, 1-3 zdania>
NIEDOPASOWANIE: <"brak" albo "numer_punktu: krótkie uzasadnienie po polsku">
Bez dodatkowych komentarzy, nagłówków ani markdown."""


def _is_configured():
    return bool(
        AzureOpenAI
        and settings.AZURE_OPENAI_ENDPOINT
        and settings.AZURE_OPENAI_KEY
        and settings.AZURE_OPENAI_DEPLOYMENT
    )


def suggest_nc_description(photo=None, past_examples=None, item=None, all_points=None):
    """Zwraca dict {available, suggestion, mismatch_point, mismatch_reason, error}.
    Nigdy nie podnosi wyjątku.

    item - ChecklistItem, punkt przy którym audytor jest w danym momencie (do zbudowania
    kontekstu sekcja/podsekcja/treść punktu).
    all_points - lista (numer, opis) wszystkich punktów tego szablonu checklisty, do
    wskazania niedopasowania."""
    if not _is_configured():
        return {"available": False, "suggestion": None, "mismatch_point": None,
                "mismatch_reason": None, "error": "Azure OpenAI nie jest skonfigurowane."}
    if not photo:
        return {"available": True, "suggestion": None, "mismatch_point": None,
                "mismatch_reason": None, "error": "Brak zdjęcia."}

    try:
        client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=1,
        )
        image_b64 = base64.b64encode(photo.read()).decode("utf-8")
        examples_text = "\n".join(f"- {e}" for e in (past_examples or [])) or "(brak wcześniejszych przykładów)"

        if item is not None:
            section_name = f"{item.subsection.section.label}. {item.subsection.section.name}"
            subsection_name = f"{item.subsection.number}. {item.subsection.name}"
            item_number, item_description = item.number, item.description
        else:
            section_name = subsection_name = "(nieznana)"
            item_number, item_description = "?", "(brak danych o punkcie)"

        points_text = "\n".join(f"- {num}: {desc}" for num, desc in (all_points or [])) or "(brak danych)"

        prompt = PROMPT_TEMPLATE.format(
            section_name=section_name, subsection_name=subsection_name,
            item_number=item_number, item_description=item_description,
            all_points=points_text, examples=examples_text,
        )

        response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
            max_tokens=300,
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip()

        suggestion, mismatch_point, mismatch_reason = None, None, None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.upper().startswith("OPIS:"):
                suggestion = line.split(":", 1)[1].strip() or None
            elif line.upper().startswith("NIEDOPASOWANIE:"):
                value = line.split(":", 1)[1].strip()
                if value and value.lower() not in ("brak", "brak.", "-"):
                    parts = value.split(":", 1)
                    mismatch_point = parts[0].strip()
                    mismatch_reason = parts[1].strip() if len(parts) > 1 else ""

        if suggestion is None and mismatch_point is None:
            # model nie trzymał się formatu - potraktuj całość jako opis
            suggestion = text

        return {
            "available": True, "suggestion": suggestion,
            "mismatch_point": mismatch_point, "mismatch_reason": mismatch_reason, "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - podpowiedź AI nie może wywalić formularza
        return {"available": True, "suggestion": None, "mismatch_point": None,
                "mismatch_reason": None, "error": str(exc)}


SUMMARY_PROMPT_TEMPLATE = """Jesteś asystentem audytora GMP/GHP w zakładzie produkcji spożywczej.
Na podstawie listy niezgodności znalezionych podczas inspekcji (tylko numer punktu checklisty
i opis - bez nazwisk, działów ani lokalizacji) napisz podsumowanie inspekcji metodą "hamburgera":
1) krótkie, konkretne pozytywy - co poszło dobrze (np. liczba punktów bez niezgodności,
   ogólne wrażenie porządku), 2) rzeczowe, konstruktywne punkty tego, co wymaga poprawy,
   bez oskarżycielskiego tonu, 3) krótka pozytywna zachęta na przyszłość.

Punkty bez niezgodności: {ok_count} z {total_count}.
Znalezione niezgodności (punkt - opis):
{items}

Odpowiedz WYŁĄCZNIE w formacie wypunktowanym (każdy punkt w osobnej linii,
zaczynający się od "* ", 1 krótkie zdanie na punkt, 2-4 punkty na sekcję):
CO_BYLO_OK:
* <punkt>
* <punkt>
DO_POPRAWY:
* <punkt>
* <punkt>
Bez dodatkowych komentarzy, nagłówków ani markdown poza gwiazdkami punktów."""


def suggest_inspection_summary(nc_points, ok_count, total_count):
    """Generuje propozycję podsumowania inspekcji (metoda hamburgera) na bazie
    ZANONIMIZOWANYCH danych - nc_points to lista (punkt_checklisty, opis), bez
    nazwisk, działów ani lokalizacji. Zwraca dict {available, summary_good,
    summary_to_fix, error}. Nigdy nie podnosi wyjątku."""
    if not _is_configured():
        return {"available": False, "summary_good": None, "summary_to_fix": None,
                "error": "Azure OpenAI nie jest skonfigurowane."}
    if not nc_points:
        return {"available": True, "summary_good": None, "summary_to_fix": None,
                "error": "Brak niezgodności do podsumowania."}

    try:
        client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=1,
        )
        items_text = "\n".join(f"- {label or 'Brak punktu odniesienia'}: {desc}" for label, desc in nc_points)

        response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=[{
                "role": "user",
                "content": SUMMARY_PROMPT_TEMPLATE.format(
                    ok_count=ok_count, total_count=total_count, items=items_text,
                ),
            }],
            max_tokens=400,
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip()
        good_lines, fix_lines = [], []
        section = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.upper().startswith("CO_BYLO_OK"):
                section = "good"
                continue
            if line.upper().startswith("DO_POPRAWY"):
                section = "fix"
                continue
            line = re.sub(r"^[-•*]\s*", "", line)
            if section == "good":
                good_lines.append(f"* {line}")
            elif section == "fix":
                fix_lines.append(f"* {line}")
        summary_good = "\n".join(good_lines) or None
        summary_to_fix = "\n".join(fix_lines) or None
        if not summary_good and not summary_to_fix:
            # model nie trzymał się formatu - zwróć całość jako "do poprawy", niech audytor poprawi
            summary_to_fix = text
        return {"available": True, "summary_good": summary_good, "summary_to_fix": summary_to_fix, "error": None}
    except Exception as exc:  # noqa: BLE001 - podpowiedź AI nie może wywalić formularza
        return {"available": True, "summary_good": None, "summary_to_fix": None, "error": str(exc)}
