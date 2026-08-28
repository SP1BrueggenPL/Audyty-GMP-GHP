from django import template

register = template.Library()


@register.filter
def dictkey(mapping, key):
    """Odczyt słownika po kluczu, który nie jest stałym identyfikatorem
    (np. mapping|dictkey:item.id) - Django nie wspiera tego natywnie."""
    if not mapping:
        return None
    return mapping.get(key)
