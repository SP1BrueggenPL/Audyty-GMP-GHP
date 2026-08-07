"""
Dane startowe do testów lokalnych: konto administratora (login+hasło, do
panelu /admin/) oraz konta pracownicze logowane wyłącznie 5-cyfrowym numerem
chipa - audytorzy (lista z arkusza pomocniczego obowiązujących checklist),
helpdesk i przykładowe osoby zmianowe (przedstawiciele obszaru) z przypisaną
zmianą i rolą działową (Pakownia/Produkcja, Techniczny, Logistyka).

UWAGA: konto "admin" jest kontem TESTOWYM z prostym hasłem — wyłącznie do
pracy na środowisku deweloperskim. Przed wdrożeniem produkcyjnym musi być
utworzone przez standardowy proces IT, zgodnie z polityką bezpieczeństwa.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Department, Role

User = get_user_model()

# (numer chipa, imię i nazwisko)
AUDITORS = [
    ("10001", "Klaudia Buława"), ("10002", "Dorota Cąkała"), ("10003", "Paulina Chotkowska"),
    ("10004", "Gabriela Glińska"), ("10005", "Kornelia Grzybowska"), ("10006", "Patrycja Gugałka"),
    ("10007", "Agnieszka Kander"), ("10008", "Marta Kowalczyk"), ("10009", "Kacper Onisk"),
    ("10010", "Joanna Radzik"), ("10011", "Anna Sękulska-Kołodziejek"),
    ("10012", "Natalia Urbańska-Kiljańska"), ("10013", "Aleksandra Żarczyńska"),
    ("21012", "Czytnik Chip"),
]

HELPDESK_DEMO = [
    ("10020", "Ewa Dyrektor"),
]

# (numer chipa, imię i nazwisko, dział, rola, zmiana lub None dla pracowników niezmianowych)
SHIFT_STAFF = [
    ("10031", "Robert Zalech", Department.WCE, Role.PAKOWNIA_PRODUKCJA, "D"),
    ("10032", "Mariusz Ochnia", Department.WPP, Role.PAKOWNIA_PRODUKCJA, "D"),
    ("10033", "Katarzyna Nowak", Department.WPP, Role.PAKOWNIA_PRODUKCJA, "D"),
    ("10034", "Tomasz Lewandowski", Department.WCE, Role.PAKOWNIA_PRODUKCJA, "A"),
    ("10035", "Przemysław Szczepek", Department.WLS, Role.LOGISTYKA, "C"),
    ("10036", "Piotr Sękulski", Department.WED, Role.TECHNICZNY, None),
]


def _split_name(full_name):
    first, *rest = full_name.split(" ")
    return first, " ".join(rest)


class Command(BaseCommand):
    help = "Tworzy konto administratora oraz przykładowe konta pracownicze logowane numerem chipa."

    def handle(self, *args, **options):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(username="admin", password="ZmieńTeHasło123!", role=Role.ADMIN)
            self.stdout.write(self.style.WARNING("Utworzono konto testowe admin / ZmieńTeHasło123! — zmień hasło."))

        created = 0

        def upsert(chip, full_name, role, department="", shift=None):
            nonlocal created
            first, last = _split_name(full_name)
            user, was_created = User.objects.get_or_create(
                username=chip,
                defaults={"first_name": first, "last_name": last, "role": role,
                          "department": department, "shift": shift},
            )
            if was_created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            else:
                user.first_name, user.last_name = first, last
                user.role, user.department, user.shift = role, department, shift
                user.save(update_fields=["first_name", "last_name", "role", "department", "shift"])
            created += int(was_created)

        for chip, full_name in AUDITORS:
            upsert(chip, full_name, Role.AUDYTOR)

        for chip, full_name in HELPDESK_DEMO:
            upsert(chip, full_name, Role.HELPDESK)
            User.objects.filter(username=chip).update(receives_escalations=True)

        for chip, full_name, dept, role, shift in SHIFT_STAFF:
            upsert(chip, full_name, role, department=dept, shift=shift)

        self.stdout.write(self.style.SUCCESS(f"Utworzono {created} nowych kont użytkowników."))
