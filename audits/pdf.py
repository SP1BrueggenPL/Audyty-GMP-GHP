"""Generowanie PDF raportu inspekcji (xhtml2pdf) - do pobrania i załącznika e-mail."""
import io

from django.conf import settings
from django.template.loader import render_to_string
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa

# xhtml2pdf domyślnie umie tylko Helvetica/Times/Courier (WinAnsi - bez polskich
# znaków rozszerzonych: ą ć ę ł ń ś ź ż). Rejestrujemy DejaVu Sans (pełne pokrycie
# Unicode, licencja pozwala na redystrybucję, pliki w static/fonts/) bezpośrednio
# w reportlab. CSS @font-face z lokalną ścieżką zawodzi w xhtml2pdf na Windows
# (urlparse myli "C:" z prefiksem schematu URL) - obejście: rejestracja fontu
# w reportlab + podmiana wewnętrznej mapy nazw fontów xhtml2pdf, więc font
# jest dostępny od razu, bez przechodzenia przez CSS/URL. Rejestracja raz,
# przy imporcie modułu.
_FONTS_DIR = settings.BASE_DIR / "static" / "fonts"
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        "DejaVuSans", normal="DejaVuSans", bold="DejaVuSans-Bold",
        italic="DejaVuSans", boldItalic="DejaVuSans-Bold",
    )
    import xhtml2pdf.default as _xhtml2pdf_default
    _xhtml2pdf_default.DEFAULT_FONT["dejavusans"] = "DejaVuSans"
    _xhtml2pdf_default.DEFAULT_FONT["dejavusans-bold"] = "DejaVuSans-Bold"
except Exception:  # noqa: BLE001 - brak fontu nie może uniemożliwić importu modułu
    pass


def _photo_is_valid(photo):
    """xhtml2pdf/PIL wywala cały dokument na pierwszym uszkodzonym pliku obrazu -
    pomijamy zdjęcia, których nie da się otworzyć, zamiast psuć cały raport."""
    try:
        from PIL import Image
        with Image.open(photo.image.path) as im:
            im.verify()
        return True
    except Exception:  # noqa: BLE001 - dowolny błąd odczytu obrazu ma być pominięty, nie wywalać PDF-a
        return False


def render_inspection_pdf(inspection, section_results, nonconformities, app_link=""):
    """Zwraca bytes gotowego PDF-a raportu inspekcji, albo None jeśli generowanie się nie powiodło."""
    nc_data = [
        {"nc": nc, "photos": [p for p in nc.photos.all() if _photo_is_valid(p)]}
        for nc in nonconformities
    ]
    html = render_to_string("audits/inspection_report_pdf.html", {
        "inspection": inspection,
        "section_results": section_results,
        "nc_data": nc_data,
        "app_link": app_link,
    })
    buf = io.BytesIO()
    status = pisa.CreatePDF(io.StringIO(html), dest=buf)
    if status.err:
        return None
    return buf.getvalue()
