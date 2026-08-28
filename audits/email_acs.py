"""Wysyłka maila z raportem inspekcji (Azure Communication Services Email).

Wymaga zmiennych środowiskowych (patrz settings.py):
    AZURE_CONNECTION_STRING   - connection string zasobu Communication Services
    EMAIL_SENDER_ADDRESS      - zweryfikowany adres nadawcy w domenie tego zasobu

Jeśli te wartości nie są ustawione, wysyłka po prostu się nie powiedzie z czytelnym
komunikatem - reszta aplikacji (zapis raportu) działa normalnie.
"""
import base64

from django.conf import settings

try:
    from azure.communication.email import EmailClient
except ImportError:  # pragma: no cover
    EmailClient = None


def _is_configured():
    return bool(
        EmailClient
        and settings.AZURE_COMMUNICATION_CONNECTION_STRING
        and settings.EMAIL_SENDER_ADDRESS
    )


def send_report_email(subject, body_text, recipients, pdf_bytes=None, pdf_filename="raport.pdf"):
    """Wysyła e-mail z opcjonalnym załącznikiem PDF. Zwraca dict {sent, error}.
    Nigdy nie podnosi wyjątku."""
    if not _is_configured():
        return {"sent": False, "error": "Wysyłka e-mail (Azure Communication Services) nie jest skonfigurowana."}
    if not recipients:
        return {"sent": False, "error": "Brak odbiorców."}

    try:
        client = EmailClient.from_connection_string(settings.AZURE_COMMUNICATION_CONNECTION_STRING)
        message = {
            "senderAddress": settings.EMAIL_SENDER_ADDRESS,
            "content": {"subject": subject, "plainText": body_text},
            "recipients": {"to": [{"address": r} for r in recipients]},
        }
        if pdf_bytes:
            message["attachments"] = [{
                "name": pdf_filename,
                "contentType": "application/pdf",
                "contentInBase64": base64.b64encode(pdf_bytes).decode("ascii"),
            }]

        poller = client.begin_send(message)
        result = poller.result()
        status = result.get("status") if isinstance(result, dict) else None
        if status and status.lower() not in ("succeeded",):
            return {"sent": False, "error": f"Status wysyłki: {status}."}
        return {"sent": True, "error": None}
    except Exception as exc:  # noqa: BLE001 - wysyłka maila nie może wywalić zapisu raportu
        return {"sent": False, "error": str(exc)}
