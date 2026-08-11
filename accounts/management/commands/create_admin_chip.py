"""
Tworzy (albo podnosi do roli QualityAdmin już istniejące) konto logowane
5-cyfrowym numerem chipa - tak jak wszystkie konta pracownicze. Przy
pierwszym logowaniu system poprosi o ustawienie własnego 6-znakowego kodu
autoryzującego (patrz accounts/views.py::chip_login).

Konta QualityAdmin są też widoczne i zarządzalne w zakładce Użytkownicy
(łącznie z przyciskiem "Resetuj kod") - ta komenda jest głównie do
utworzenia pierwszego takiego konta z SSH, zanim ktoś w ogóle może się
zalogować, albo gdy szybciej jest wpisać komendę niż kliknąć w UI.

Użycie:
    python manage.py create_admin_chip 21012
    python manage.py create_admin_chip 21012 --imie Jan --nazwisko Kowalski
    python manage.py create_admin_chip 21012 --reset-code   # wymuś reset kodu (nawet jeśli już ustawiony)
"""
import re

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Role, User

CHIP_RE = re.compile(r"^\d{5}$")


class Command(BaseCommand):
    help = "Tworzy/aktualizuje konto z rolą Administrator logowane podanym numerem chipa."

    def add_arguments(self, parser):
        parser.add_argument("chip", help="5-cyfrowy numer chipa, np. 21012")
        parser.add_argument("--imie", default=None, help="Imię (opcjonalnie)")
        parser.add_argument("--nazwisko", default=None, help="Nazwisko (opcjonalnie)")
        parser.add_argument(
            "--reset-code", action="store_true",
            help="Wymuś reset kodu autoryzującego, nawet jeśli konto już ma ustawiony.",
        )

    def handle(self, *args, **options):
        chip = options["chip"].strip()
        if not CHIP_RE.fullmatch(chip):
            raise CommandError("Numer chipa musi mieć dokładnie 5 cyfr, np. 21012.")

        user, created = User.objects.get_or_create(username=chip)
        user.role = Role.ADMIN
        user.is_active = True
        if options["imie"]:
            user.first_name = options["imie"]
        if options["nazwisko"]:
            user.last_name = options["nazwisko"]

        code_reset = False
        if not user.has_usable_password() or options["reset_code"]:
            user.set_unusable_password()
            code_reset = True
        user.save()

        action = "Utworzono" if created else "Zaktualizowano"
        self.stdout.write(self.style.SUCCESS(
            f"{action} konto administratora: {chip} ({user.get_full_name() or 'bez nazwiska'})."
        ))
        if code_reset:
            self.stdout.write(self.style.SUCCESS(
                "Kod autoryzujący zresetowany - przy najbliższym logowaniu (ten numer na "
                "stronie głównej) system poprosi o ustawienie nowego 6-znakowego kodu."
            ))
