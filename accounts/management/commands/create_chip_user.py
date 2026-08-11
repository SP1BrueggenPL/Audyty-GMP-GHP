"""
Tworzy (albo aktualizuje) zwykłe konto pracownicze logowane numerem chipa -
do użycia z konsoli SSH/Kudu, gdy szybciej jest wpisać komendę niż wejść
w zakładkę Użytkownicy.

Przy pierwszym logowaniu system poprosi o ustawienie własnego 6-znakowego
kodu autoryzującego (patrz accounts/views.py::chip_login).

Użycie:
    python manage.py create_chip_user 12345 --imie Jan --nazwisko Kowalski --rola AUDYTOR
    python manage.py create_chip_user 12345 --imie Jan --nazwisko Kowalski --rola PAKOWNIA_PRODUKCJA --dzial WCE --zmiana A
    python manage.py create_chip_user 12345 --reset-code

Dostępne role: ADMIN, HELPDESK, AUDYTOR, PAKOWNIA_PRODUKCJA, TECHNICZNY, LOGISTYKA
(dla ADMIN użyj raczej dedykowanej komendy create_admin_chip).
Dostępne działy: WCE, WPP, KONF, WLS, WED. Zmiana: A, B, C, D (opcjonalnie).
"""
import re

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Department, Role, Shift, User

CHIP_RE = re.compile(r"^\d{5}$")


class Command(BaseCommand):
    help = "Tworzy/aktualizuje konto pracownicze (dowolna rola poza Administrator) logowane numerem chipa."

    def add_arguments(self, parser):
        parser.add_argument("chip", help="5-cyfrowy numer chipa, np. 12345")
        parser.add_argument("--imie", default=None, help="Imię (opcjonalnie)")
        parser.add_argument("--nazwisko", default=None, help="Nazwisko (opcjonalnie)")
        parser.add_argument(
            "--rola", default=Role.AUDYTOR, choices=[r.value for r in Role if r != Role.ADMIN],
            help="Rola (domyślnie AUDYTOR).",
        )
        parser.add_argument("--dzial", default="", choices=[""] + [d.value for d in Department], help="Dział (opcjonalnie).")
        parser.add_argument("--zmiana", default=None, choices=[s.value for s in Shift], help="Zmiana A/B/C/D (opcjonalnie).")
        parser.add_argument("--eskalacje", action="store_true", help="Włącz otrzymywanie powiadomień eskalacyjnych.")
        parser.add_argument(
            "--reset-code", action="store_true",
            help="Wymuś reset kodu autoryzującego, nawet jeśli konto już ma ustawiony.",
        )

    def handle(self, *args, **options):
        chip = options["chip"].strip()
        if not CHIP_RE.fullmatch(chip):
            raise CommandError("Numer chipa musi mieć dokładnie 5 cyfr, np. 12345.")

        user, created = User.objects.get_or_create(username=chip)
        user.role = options["rola"]
        user.department = options["dzial"]
        user.shift = options["zmiana"]
        user.is_active = True
        if options["imie"]:
            user.first_name = options["imie"]
        if options["nazwisko"]:
            user.last_name = options["nazwisko"]
        if options["eskalacje"]:
            user.receives_escalations = True

        code_reset = False
        if not user.has_usable_password() or options["reset_code"]:
            user.set_unusable_password()
            code_reset = True
        user.save()

        action = "Utworzono" if created else "Zaktualizowano"
        self.stdout.write(self.style.SUCCESS(
            f"{action} konto: {chip} ({user.get_full_name() or 'bez nazwiska'}), rola: {user.get_role_display()}."
        ))
        if code_reset:
            self.stdout.write(self.style.SUCCESS(
                "Kod autoryzujący zresetowany - przy najbliższym logowaniu (ten numer na "
                "stronie głównej) system poprosi o ustawienie nowego 6-znakowego kodu."
            ))
