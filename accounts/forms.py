import re

from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()

CHIP_NUMBER_RE = re.compile(r"^\d{5}$")


class UserForm(forms.ModelForm):
    """Uproszczony formularz konta pracownika - logowanie wyłącznie 5-cyfrowym
    numerem chipa, bez hasła czy telefonu. E-mail jest opcjonalny - przydaje się
    do wysyłki przypomnień/eskalacji o niezgodnościach oraz raportów inspekcji.
    Imię i nazwisko wpisuje się jako jedno pole, rozbijane na first_name/
    last_name przy zapisie."""

    full_name = forms.CharField(
        label="Imię i nazwisko", max_length=300,
        widget=forms.TextInput(attrs={"placeholder": "np. Jan Kowalski"}),
    )

    class Meta:
        model = User
        fields = ["username", "email", "role", "department", "shift", "receives_escalations", "is_active"]
        labels = {"username": "Numer chipa (login)", "email": "Adres e-mail (opcjonalnie)"}

    field_order = [
        "username", "full_name", "email", "role", "department", "shift",
        "receives_escalations", "is_active",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(self.field_order)
        self.fields["username"].widget.attrs.update({
            "placeholder": "np. 21012", "maxlength": 5, "pattern": r"\d{5}",
            "inputmode": "numeric",
        })
        self.fields["email"].required = False
        self.fields["email"].widget.attrs.update({"placeholder": "np. jan.kowalski@brueggen.com"})
        self.fields["username"].help_text = "Dokładnie 5 cyfr - numer chipa pracowniczego używany do logowania."
        if self.instance and self.instance.pk:
            self.fields["full_name"].initial = f"{self.instance.first_name} {self.instance.last_name}".strip()

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not CHIP_NUMBER_RE.fullmatch(username):
            raise forms.ValidationError("Numer chipa musi składać się z dokładnie 5 cyfr, np. 21012.")
        return username

    def clean_full_name(self):
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise forms.ValidationError("Podaj imię i nazwisko.")
        return full_name

    def save(self, commit=True):
        user = super().save(commit=False)
        first, *rest = self.cleaned_data["full_name"].split(" ")
        user.first_name = first
        user.last_name = " ".join(rest)
        if not user.pk:
            user.set_unusable_password()
        if commit:
            user.save()
        return user
