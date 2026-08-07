"""
Tworzy (albo podnosi do roli Administrator już istniejące) konto logowane
5-cyfrowym numerem chipa - bez hasła, tak jak wszystkie konta pracownicze.

Użycie:
    python manage.py create_admin_chip 21012
    python manage.py create_admin_chip 21012 --imie Jan --nazwisko Kowalski
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
        if not user.has_usable_password():
            user.set_unusable_password()
        user.save()

        action = "Utworzono" if created else "Zaktualizowano"
        self.stdout.write(self.style.SUCCESS(
            f"{action} konto administratora: {chip} ({user.get_full_name() or 'bez nazwiska'}). "
            "Logowanie: wpisanie tego numeru na stronie głównej, bez hasła."
        ))
