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

from django.conf import settings

try:
    from openai import AzureOpenAI
except ImportError:  # pragma: no cover
    AzureOpenAI = None

PROMPT_TEMPLATE = """Jesteś asystentem audytora GMP/GHP w zakładzie produkcji spożywczej.
Na podstawie zdjęcia oraz przykładów wcześniej zapisanych niezgodności dla tego samego
punktu checklisty, zaproponuj krótki, konkretny opis niezgodności (1-3 zdania, po polsku,
w stylu audytowym: co i gdzie jest niezgodne). Nie wymyślaj lokalizacji, których nie widać
na zdjęciu - jeśli nie jesteś w stanie jej określić, opisz tylko charakter niezgodności.

Przykłady wcześniejszych opisów niezgodności dla tego punktu (dla stylu/kontekstu, nie
kopiuj ich treści dosłownie):
{examples}

Zwróć wyłącznie proponowany opis niezgodności, bez dodatkowych komentarzy."""


def _is_configured():
    return bool(
        AzureOpenAI
        and settings.AZURE_OPENAI_ENDPOINT
        and settings.AZURE_OPENAI_KEY
        and settings.AZURE_OPENAI_DEPLOYMENT
    )


def suggest_nc_description(photo=None, past_examples=None):
    """Zwraca dict {available, suggestion, error}. Nigdy nie podnosi wyjątku."""
    if not _is_configured():
        return {"available": False, "suggestion": None, "error": "Azure OpenAI nie jest skonfigurowane."}
    if not photo:
        return {"available": True, "suggestion": None, "error": "Brak zdjęcia."}

    try:
        client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        image_b64 = base64.b64encode(photo.read()).decode("utf-8")
        examples_text = "\n".join(f"- {e}" for e in (past_examples or [])) or "(brak wcześniejszych przykładów)"

        response = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT_TEMPLATE.format(examples=examples_text)},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
            max_tokens=200,
            temperature=0.4,
        )
        suggestion = response.choices[0].message.content.strip()
        return {"available": True, "suggestion": suggestion, "error": None}
    except Exception as exc:  # noqa: BLE001 - podpowiedź AI nie może wywalić formularza
        return {"available": True, "suggestion": None, "error": str(exc)}
