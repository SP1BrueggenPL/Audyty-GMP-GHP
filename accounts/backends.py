from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

User = get_user_model()


class ChipBackend(BaseBackend):
    """Logowanie chipem/kartą pracowniczą — numer chipa = login, bez hasła.

    Fizyczne posiadanie chipa jest tu traktowane jako czynnik uwierzytelniający
    (analogicznie do czytnika RFID przy wejściu na produkcję). Czytnik USB
    podłączony do tabletu/kiosku działa w trybie "klawiatury" — po zeskanowaniu
    wpisuje numer chipa i wysyła Enter, co odpowiada zwykłemu wpisaniu numeru
    i zatwierdzeniu formularza.
    """

    def authenticate(self, request, chip_code=None, **kwargs):
        if not chip_code:
            return None
        try:
            return User.objects.get(username=chip_code, is_active=True)
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return None
