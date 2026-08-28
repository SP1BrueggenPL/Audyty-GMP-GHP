from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department


class AreaCode(models.TextChoices):
    """Typ checklisty / obszaru, dla którego audytor wybiera formularz."""
    WCE_WPP = "WCE_WPP", "WCE/WPP - Produkcja i Pakownia"
    WLS = "WLS", "WLS - Magazyn"
    WED = "WED", "WED - Dział techniczny"


class Shift(models.TextChoices):
    A = "A", "A"
    B = "B", "B"
    C = "C", "C"
    D = "D", "D"
    ND = "n/d", "nie dotyczy"


# ---------------------------------------------------------------------------
# Struktura checklisty (edytowalna w panelu admina, wgrywana z realnych
# formularzy CD-xxxx obowiązujących w zakładzie)
# ---------------------------------------------------------------------------

class ChecklistTemplate(models.Model):
    area_code = models.CharField(max_length=10, choices=AreaCode.choices)
    name = models.CharField(max_length=200, help_text="np. Inspekcja GMP/GHP - PRODUKCJA/PAKOWNIA")
    document_code = models.CharField(max_length=50, help_text="Numer i wersja dokumentu, np. CD-00004592-3")
    version_note = models.CharField(max_length=100, blank=True, help_text="np. zm. D, 19.03.2026")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["area_code", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.document_code})"

    @property
    def max_points_total(self):
        return sum(s.max_points for s in self.sections.all())


class ChecklistSection(models.Model):
    """Zakres wymagań, np. 'I. Higiena - porządek'."""
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="sections")
    order = models.PositiveSmallIntegerField(default=0)
    label = models.CharField(max_length=10, help_text="Numeracja rzymska, np. I, II, III")
    name = models.CharField(max_length=200)
    max_points = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["template", "order"]

    def __str__(self):
        return f"{self.label}. {self.name}"


class ChecklistSubsection(models.Model):
    """Grupa punktów w ramach zakresu, np. '1. Drobny sprzęt do sprzątania'."""
    section = models.ForeignKey(ChecklistSection, on_delete=models.CASCADE, related_name="subsections")
    order = models.PositiveSmallIntegerField(default=0)
    number = models.CharField(max_length=10, help_text="np. 1, 2, 3")
    name = models.CharField(max_length=400)

    class Meta:
        ordering = ["section", "order"]

    def __str__(self):
        return f"{self.number}. {self.name}"


class ChecklistItem(models.Model):
    """Pojedynczy punkt kontrolny, np. '1.1' z pełnym opisem wymagania."""
    subsection = models.ForeignKey(ChecklistSubsection, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveSmallIntegerField(default=0)
    number = models.CharField(max_length=10, help_text="np. 1.1, 2.3")
    description = models.TextField()

    class Meta:
        ordering = ["subsection", "order"]

    def __str__(self):
        return f"{self.number} {self.description[:60]}"


# ---------------------------------------------------------------------------
# Inspekcja (cyfrowy odpowiednik wypełnionej checklisty + raportu)
# ---------------------------------------------------------------------------

class InspectionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Wersja robocza"
    SUBMITTED = "SUBMITTED", "Zakończona"
    REPORT_SENT = "REPORT_SENT", "Raport wysłany"
    CLOSED = "CLOSED", "Zamknięta (wszystkie NC zamknięte)"


class Inspection(models.Model):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT, related_name="inspections")
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name="Data/godzina inspekcji")
    area_detail = models.CharField(max_length=200, blank=True, verbose_name="Obszar")
    shift = models.CharField(max_length=5, choices=Shift.choices, default=Shift.ND)
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="inspections_led",
        verbose_name="Osoba przeprowadzająca inspekcję",
    )
    area_representatives = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="represented_inspections",
        verbose_name="Przedstawiciele obszaru",
        help_text="Domyślnie osoby z wybranej zmiany - lista może być modyfikowana przed zapisem inspekcji.",
    )

    # Pola zależne od typu obszaru (WCE/WPP: linie; WED: pomieszczenia)
    lines_working = models.TextField(blank=True, verbose_name="Linie pracujące")
    lines_not_working_cleaning = models.TextField(blank=True, verbose_name="Linie niepracujące (mycie)")
    lines_not_working_stopped = models.TextField(blank=True, verbose_name="Linie niepracujące (postój)")
    rooms_checked = models.TextField(
        blank=True, verbose_name="Sprawdzone pomieszczenia/miejsca",
        help_text="Jedna pozycja na linię - dla inspekcji WED",
    )

    status = models.CharField(max_length=20, choices=InspectionStatus.choices, default=InspectionStatus.DRAFT)
    summary_good = models.TextField(blank=True, verbose_name="Podsumowanie - co było ok")
    summary_to_fix = models.TextField(blank=True, verbose_name="Podsumowanie - co do poprawki")
    report_recipients = models.CharField(max_length=500, blank=True, help_text="Adresy e-mail rozdzielone przecinkiem")
    report_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inspected_at"]

    def __str__(self):
        return f"{self.template.get_area_code_display()} - {self.inspected_at:%d.%m.%Y %H:%M}"

    def get_absolute_url(self):
        return reverse("inspection_detail", args=[self.pk])

    @property
    def max_points_total(self):
        return sum(s.max_points for s in self.template.sections.all())

    @property
    def area_representatives_display(self):
        return ", ".join(str(u) for u in self.area_representatives.all())

    @property
    def extra_nc_count(self):
        return self.nonconformities.filter(is_extra=True).count()

    @property
    def points_total(self):
        section_points = sum(r.points_awarded or 0 for r in self.section_results.all())
        return max(0, section_points - self.extra_nc_count)

    @property
    def result_percent(self):
        total_max = self.max_points_total
        if not total_max:
            return None
        return round(100 * self.points_total / total_max, 1)

    @property
    def nonconformity_count(self):
        return self.nonconformities.count()

    @property
    def open_nonconformity_count(self):
        return self.nonconformities.exclude(status=NCStatus.WDROZONE).count()


class InspectionSectionResult(models.Model):
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="section_results")
    section = models.ForeignKey(ChecklistSection, on_delete=models.PROTECT)
    points_awarded = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("inspection", "section")]
        ordering = ["section__order"]

    def __str__(self):
        return f"{self.inspection} / {self.section.label} = {self.points_awarded}/{self.section.max_points}"

    @property
    def percent(self):
        if not self.section.max_points:
            return None
        return round(100 * self.points_awarded / self.section.max_points, 1)


class ItemResult(models.TextChoices):
    OK = "OK", "Zgodność"
    NC = "NC", "Niezgodność"
    NA = "NA", "Nie dotyczy"


class InspectionItemResult(models.Model):
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="item_results")
    item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT)
    result = models.CharField(max_length=5, choices=ItemResult.choices, default=ItemResult.OK)
    note = models.TextField(blank=True)

    class Meta:
        unique_together = [("inspection", "item")]
        ordering = ["item__subsection__section__order", "item__subsection__order", "item__order"]

    def __str__(self):
        return f"{self.item.number} - {self.get_result_display()}"


# ---------------------------------------------------------------------------
# Rejestr niezgodności (cyfrowy odpowiednik arkusza NIEZGODNOŚCI GMP/GHP)
# ---------------------------------------------------------------------------

class NCStatus(models.TextChoices):
    W_TOKU = "W_TOKU", "W toku"
    WDROZONE = "WDROZONE", "Wdrożone"
    ANULOWANE = "ANULOWANE", "Anulowane"


class NonConformity(models.Model):
    number = models.CharField(max_length=30, unique=True, editable=False)

    inspection = models.ForeignKey(
        Inspection, on_delete=models.CASCADE, related_name="nonconformities", null=True, blank=True,
    )
    checklist_item = models.ForeignKey(
        ChecklistItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="nonconformities",
    )
    is_extra = models.BooleanField(
        default=False, verbose_name="Niezgodność dodatkowa",
        help_text="Dodana ponad standardowe zaznaczenie punktu checklisty - odlicza punkt od ogólnej "
                   "puli wyniku inspekcji, a nie od konkretnej sekcji.",
    )

    inspection_date = models.DateField(verbose_name="Data inspekcji")
    entry_date = models.DateField(auto_now_add=True, verbose_name="Data wpisu do rejestru")
    department = models.CharField(max_length=10, choices=Department.choices, verbose_name="Obszar")
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="nonconformities_raised",
        verbose_name="Osoba przeprowadzająca inspekcję",
    )
    shift = models.CharField(max_length=5, choices=Shift.choices, default=Shift.ND)
    area_representative = models.CharField(max_length=300, blank=True, verbose_name="Przedstawiciel obszaru")

    gmp_category = models.CharField(max_length=200, blank=True, verbose_name="Obszar GMP/GHP")
    checklist_point_label = models.CharField(
        max_length=30, blank=True, verbose_name="Punkt checklisty",
        help_text="np. 1.1, 3.4 lub 'Brak punktu odniesienia'",
    )
    point_description = models.CharField(max_length=400, blank=True, verbose_name="Opis punktu")
    location_detail = models.CharField(max_length=200, blank=True, verbose_name="Obszar / lokalizacja")

    description = models.TextField(verbose_name="Opis niezgodności")

    responsible_person = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_nonconformities", verbose_name="Osoba odpowiedzialna za obszar",
    )

    # Wypełnia osoba odpowiedzialna za obszar
    root_cause = models.TextField(blank=True, verbose_name="Źródło problemu")
    corrective_action = models.TextField(blank=True, verbose_name="Działania korekcyjne")
    corrective_action_date = models.DateField(null=True, blank=True, verbose_name="Data podjęcia działań korekcyjnych")
    preventive_action = models.TextField(blank=True, verbose_name="Działania korygujące")
    planned_preventive_date = models.DateField(null=True, blank=True, verbose_name="Planowana data wprowadzenia działań korygujących")
    actual_preventive_date = models.DateField(null=True, blank=True, verbose_name="Faktyczna data wprowadzenia działań korygujących")

    # Wypełnia audytor
    status = models.CharField(max_length=10, choices=NCStatus.choices, default=NCStatus.W_TOKU, verbose_name="Status działań")
    auditor_comment = models.TextField(blank=True, verbose_name="Uwagi audytora / inne")

    reminder_count = models.PositiveSmallIntegerField(default=0)
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inspection_date", "-id"]
        verbose_name = "Niezgodność"
        verbose_name_plural = "Niezgodności"

    def __str__(self):
        return f"{self.number} - {self.department} - {self.description[:50]}"

    def get_absolute_url(self):
        return reverse("nonconformity_detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.number:
            year = (self.inspection_date or timezone.localdate()).year
            last = NonConformity.objects.filter(number__startswith=f"{year}-").order_by("-id").first()
            seq = 1
            if last:
                try:
                    seq = int(last.number.split("-")[-1]) + 1
                except ValueError:
                    seq = NonConformity.objects.filter(inspection_date__year=year).count() + 1
            self.number = f"{year}-{seq:04d}"
        super().save(*args, **kwargs)

    @property
    def period(self):
        return f"{self.inspection_date.month:02d}.{self.inspection_date.year}"

    @property
    def is_responsible_part_filled(self):
        return bool(self.root_cause and self.corrective_action and self.preventive_action)

    @property
    def days_open(self):
        if self.status == NCStatus.WDROZONE:
            return None
        return (timezone.localdate() - self.entry_date).days

    @property
    def is_due_for_reminder(self):
        if self.status != NCStatus.W_TOKU or self.is_responsible_part_filled:
            return False
        days = self.days_open or 0
        return days >= settings.NC_REMINDER_AFTER_DAYS

    @property
    def is_due_for_escalation(self):
        if self.status != NCStatus.W_TOKU or self.is_responsible_part_filled:
            return False
        days = self.days_open or 0
        return days >= settings.NC_ESCALATION_AFTER_DAYS and not self.escalated_at


def nc_photo_path(instance, filename):
    return f"niezgodnosci/{instance.nonconformity.number}/{filename}"


class NCPhotoKind(models.TextChoices):
    NIEZGODNOSC = "NIEZGODNOSC", "Zdjęcie niezgodności"
    DOWOD = "DOWOD", "Dowód podjętych działań"


class NonConformityPhoto(models.Model):
    nonconformity = models.ForeignKey(NonConformity, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=nc_photo_path)
    kind = models.CharField(max_length=15, choices=NCPhotoKind.choices, default=NCPhotoKind.NIEZGODNOSC)
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"Zdjęcie {self.get_kind_display()} - {self.nonconformity.number}"
