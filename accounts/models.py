from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class Department(models.TextChoices):
    WCE = "WCE", "WCE - Produkcja"
    WPP = "WPP", "WPP - Pakownia"
    KONF = "KONF", "MIX - Konfekcjonowanie"
    WLS = "WLS", "WLS - Magazyn"
    WED = "WED", "WED - Dział techniczny"


class Shift(models.TextChoices):
    A = "A", "A"
    B = "B", "B"
    C = "C", "C"
    D = "D", "D"


class Role(models.TextChoices):
    ADMIN = "ADMIN", "QualityAdmin"
    HELPDESK = "HELPDESK", "Helpdesk"
    AUDYTOR = "AUDYTOR", "Audytor"
    PAKOWNIA_PRODUKCJA = "PAKOWNIA_PRODUKCJA", "Pakownia / Produkcja"
    TECHNICZNY = "TECHNICZNY", "Techniczny"
    LOGISTYKA = "LOGISTYKA", "Logistyka"
    UZYTKOWNIK_OBSZARU = "UZYTKOWNIK_OBSZARU", "Użytkownik obszaru"


# Role -> działy (Department), dla których ta rola widzi niezgodności / raporty.
# ADMIN i HELPDESK nie są tu wymieniane - widzą wszystkie działy (patrz User.department_scope).
ROLE_DEPARTMENTS = {
    Role.PAKOWNIA_PRODUKCJA: [Department.WCE, Department.WPP, Department.KONF],
    Role.TECHNICZNY: [Department.WED],
    Role.LOGISTYKA: [Department.WLS],
}

ROLES_WITH_FULL_ACCESS = {Role.ADMIN, Role.HELPDESK, Role.AUDYTOR}


def eligible_area_users(department=None, shift=None):
    """Osoby, które można wybrać jako przedstawiciela obszaru inspekcji albo
    osobę odpowiedzialną za niezgodność. Obejmuje TRZY grupy:
    1) rola "Użytkownik obszaru" - bez działu, uniwersalna dla każdego
       obszaru/działu (ta rola celowo nie ma pola Dział),
    2) rola działowa (Pakownia/Produkcja, Techniczny, Logistyka), której
       ROLE_DEPARTMENTS obejmuje dany dział - te role już z definicji
       należą do tego działu, niezależnie od pola Dział na koncie,
    3) KAŻDA osoba (niezależnie od roli) przypisana do wskazanej zmiany -
       na inspekcji może pomagać/być odpowiedzialna dowolna osoba z tej
       samej zmiany, nie tylko ta z "właściwą" rolą.
    Gdy department i shift to None, zwraca wszystkich z roli "Użytkownik
    obszaru" oraz wszystkich z jakąkolwiek rolą działową (do ogólnych list
    wyboru, np. formularz ad-hoc niezgodności bez znanego działu/zmiany)."""
    if department or shift:
        query = Q(role=Role.UZYTKOWNIK_OBSZARU)  # uniwersalna, zawsze widoczna
        if department:
            dept_roles = [role for role, depts in ROLE_DEPARTMENTS.items() if department in depts]
            query |= Q(role__in=dept_roles)
        if shift:
            query |= Q(shift=shift)
        return User.objects.filter(query)
    return User.objects.filter(
        Q(role=Role.UZYTKOWNIK_OBSZARU) | Q(role__in=list(ROLE_DEPARTMENTS.keys()))
    )


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AUDYTOR)
    department = models.CharField(
        max_length=10, choices=Department.choices, blank=True,
        help_text="Dział tej osoby (dla ról Pakownia/Produkcja, Techniczny, Logistyka wynika z roli, "
                   "ale można doprecyzować np. WCE vs WPP).",
    )
    shift = models.CharField(
        max_length=2, choices=Shift.choices, blank=True, null=True,
        verbose_name="Zmiana",
        help_text="Tylko dla pracowników zmianowych - używane do automatycznego dodawania "
                   "przedstawicieli obszaru podczas inspekcji. Puste pole = pracownik niezmianowy.",
    )
    phone = models.CharField(max_length=30, blank=True)
    receives_escalations = models.BooleanField(
        default=False,
        help_text="Osoba z tej listy otrzyma powiadomienie, gdy niezgodność jest przeterminowana (eskalacja).",
    )

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        full = self.get_full_name()
        return full if full else self.username

    def save(self, *args, **kwargs):
        # Dostęp do panelu Django /admin/ (surowa baza) mają tylko
        # superużytkownicy i rola Helpdesk (wsparcie techniczne). QualityAdmin
        # ma te same uprawnienia administracyjne w aplikacji, ale zarządza
        # wszystkim przez własne, dopieszczone ekrany, nie przez surowy panel.
        if not self.is_superuser:
            self.is_staff = self.role == Role.HELPDESK
        super().save(*args, **kwargs)

    @property
    def is_auditor(self):
        return self.role == Role.AUDYTOR or self.is_superuser

    @property
    def has_full_access(self):
        return self.is_superuser or self.role in ROLES_WITH_FULL_ACCESS

    @property
    def can_run_inspections(self):
        return self.is_superuser or self.role in {Role.ADMIN, Role.HELPDESK, Role.AUDYTOR}

    @property
    def can_view_reports(self):
        """Zakładka Raporty - tylko QualityAdmin i Helpdesk (nie Audytor,
        mimo że Audytor ma has_full_access do danych)."""
        return self.is_superuser or self.role in {Role.ADMIN, Role.HELPDESK}

    @property
    def is_admin_role(self):
        """QualityAdmin i Helpdesk mają te same uprawnienia administracyjne
        w aplikacji (Użytkownicy, edytor checklisty, edycja/usuwanie
        inspekcji i niezgodności). Helpdesk dodatkowo ma dostęp do panelu
        Django /admin/ (patrz User.save())."""
        return self.is_superuser or self.role in {Role.ADMIN, Role.HELPDESK}

    @property
    def department_scope(self):
        """Lista kodów działów (Department) widocznych dla tej osoby w rejestrze/raportach.
        None = brak ograniczenia (widzi wszystko)."""
        if self.has_full_access:
            return None
        depts = ROLE_DEPARTMENTS.get(self.role)
        if depts:
            return [d.value for d in depts]
        return [self.department] if self.department else []
