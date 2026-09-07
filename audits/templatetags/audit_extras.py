import re

from django import template

register = template.Library()


@register.filter
def dictkey(mapping, key):
    """Odczyt słownika po kluczu, który nie jest stałym identyfikatorem
    (np. mapping|dictkey:item.id) - Django nie wspiera tego natywnie."""
    if not mapping:
        return None
    return mapping.get(key)


_BULLET_PREFIX_RE = re.compile(r"^[-•*]\s*")


@register.filter
def bulletlines(text):
    """Dzieli tekst (np. podsumowanie wygenerowane przez AI) na listę punktów -
    jedna niepusta linia = jeden punkt, wiodący myślnik/kropka jest usuwany."""
    if not text:
        return []
    lines = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.append(_BULLET_PREFIX_RE.sub("", line))
    return lines
