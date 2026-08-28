from accounts.models import Role
from django import forms
from django.contrib.auth import get_user_model

from .models import AreaCode, Department, Inspection, NonConformity, Shift

User = get_user_model()

AREA_DETAIL_CHOICES = {
    AreaCode.WCE_WPP: [
        ("WCE - PRODUKCJA", "WCE - Produkcja"),
        ("WPP - PAKOWNIA", "WPP - Pakownia"),
        ("KONFEKCJONOWANIE", "Konfekcjonowanie"),
    ],
    AreaCode.WLS: [("WLS", "WLS - Magazyn")],
    AreaCode.WED: [("DZIAŁ TECHNICZNY", "Dział techniczny (WED)")],
}


def derive_department(area_code, area_detail):
    area_detail = (area_detail or "").upper()
    if area_code == AreaCode.WCE_WPP:
        if "KONFEKCJ" in area_detail:
            return Department.KONF
        return Department.WPP if "WPP" in area_detail else Department.WCE
    if area_code == AreaCode.WLS:
        return Department.WLS
    if area_code == AreaCode.WED:
        return Department.WED
    return Department.WED


class InspectionHeaderForm(forms.Form):
    inspected_at = forms.DateTimeField(
        label="Data/godzina inspekcji",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    area_detail = forms.ChoiceField(label="Obszar", choices=[])
    shift = forms.ChoiceField(label="Zmiana", choices=Shift.choices, initial=Shift.ND)
    lines_working = forms.CharField(label="Linie pracujące", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    lines_not_working_cleaning = forms.CharField(
        label="Linie niepracujące (mycie)", required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )
    lines_not_working_stopped = forms.CharField(
        label="Linie niepracujące (postój)", required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )
    rooms_checked = forms.CharField(
        label="Sprawdzone pomieszczenia/miejsca", required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Jedna pozycja na linię",
    )

    def __init__(self, *args, area_code=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area_detail"].choices = AREA_DETAIL_CHOICES.get(area_code, [])


class InspectionSummaryForm(forms.Form):
    summary_good = forms.CharField(
        label="Co było ok", required=False, widget=forms.Textarea(attrs={"rows": 4}),
    )
    summary_to_fix = forms.CharField(
        label="Co jest do poprawki", required=False, widget=forms.Textarea(attrs={"rows": 4}),
    )
    report_recipients = forms.CharField(
        label="Adresy e-mail odbiorców raportu", required=False,
        widget=forms.TextInput(attrs={"placeholder": "np. jan.kowalski@brueggen.com, dyrekcja@brueggen.com"}),
    )


class ResponsibleActionForm(forms.ModelForm):
    """Część formularza wypełniana przez osobę odpowiedzialną za obszar."""

    class Meta:
        model = NonConformity
        fields = [
            "root_cause", "corrective_action", "corrective_action_date",
            "preventive_action", "planned_preventive_date", "actual_preventive_date",
        ]
        widgets = {
            "root_cause": forms.Textarea(attrs={"rows": 3}),
            "corrective_action": forms.Textarea(attrs={"rows": 3}),
            "preventive_action": forms.Textarea(attrs={"rows": 3}),
            "corrective_action_date": forms.DateInput(attrs={"type": "date"}),
            "planned_preventive_date": forms.DateInput(attrs={"type": "date"}),
            "actual_preventive_date": forms.DateInput(attrs={"type": "date"}),
        }


class AuditorReviewForm(forms.ModelForm):
    """Część formularza wypełniana przez audytora (status i uwagi)."""

    class Meta:
        model = NonConformity
        fields = ["status", "auditor_comment", "responsible_person"]
        widgets = {"auditor_comment": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible_person"].queryset = (
            User.objects.filter(role=Role.UZYTKOWNIK_OBSZARU).order_by("last_name", "first_name")
        )


class InspectionAdminEditForm(forms.ModelForm):
    """Pełna edycja inspekcji (nagłówek + ponowne wypełnienie checklisty punkt po
    punkcie) - dostępna dla Audytora, QualityAdmin, Helpdesku i superużytkownika,
    niezależnie od statusu inspekcji. Przedstawiciele obszaru są obsługiwani poza
    tym formularzem (pole area_rep_ids w widoku, ten sam widget co przy nowej
    inspekcji) - stąd brak area_representatives w Meta.fields."""

    class Meta:
        model = Inspection
        fields = [
            "inspected_at", "area_detail", "shift", "inspector",
            "lines_working", "lines_not_working_cleaning", "lines_not_working_stopped", "rooms_checked",
            "status", "summary_good", "summary_to_fix", "report_recipients",
        ]
        widgets = {
            "inspected_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "lines_working": forms.Textarea(attrs={"rows": 2}),
            "lines_not_working_cleaning": forms.Textarea(attrs={"rows": 2}),
            "lines_not_working_stopped": forms.Textarea(attrs={"rows": 2}),
            "rooms_checked": forms.Textarea(attrs={"rows": 2}),
            "summary_good": forms.Textarea(attrs={"rows": 3}),
            "summary_to_fix": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["inspected_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["inspector"].queryset = User.objects.all().order_by("last_name", "first_name")


class StandaloneNonConformityForm(forms.ModelForm):
    """Formularz dodania niezgodności poza pełną inspekcją (np. znaleziona ad-hoc)."""

    class Meta:
        model = NonConformity
        fields = [
            "inspection_date", "department", "shift", "area_representative",
            "gmp_category", "checklist_point_label", "point_description", "location_detail",
            "description", "responsible_person",
        ]
        widgets = {
            "inspection_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible_person"].queryset = (
            User.objects.filter(role=Role.UZYTKOWNIK_OBSZARU).order_by("last_name", "first_name")
        )
