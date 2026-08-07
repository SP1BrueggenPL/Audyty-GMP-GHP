"""
Edytor treści checklisty w samej aplikacji (bez wchodzenia do Django admin) -
dostępny tylko dla roli Administrator. Trzy poziomy edycji, zgodnie ze
strukturą checklisty: szablon -> sekcje (zakresy wymagań) -> podsekcje ->
punkty kontrolne.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render

from .models import ChecklistItem, ChecklistSection, ChecklistSubsection, ChecklistTemplate


def _require_admin_role(request):
    if request.user.is_admin_role:
        return True
    messages.error(request, "Edycja treści checklisty jest dostępna tylko dla administratora.")
    return False


class ChecklistTemplateMetaForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplate
        fields = ["name", "document_code", "version_note", "is_active"]


# extra=0: nowe wiersze dodawane przez JS (klon szablonu <template>), a nie przez
# automatyczny dodatkowy formularz Django - unika to false-positive walidacji
# "puste" wiersza, którą wywołuje domyślna wartość (default=0) pól liczbowych.
SectionFormSet = inlineformset_factory(
    ChecklistTemplate, ChecklistSection,
    fields=["label", "name", "max_points", "order"],
    extra=0, can_delete=True,
)

SubsectionFormSet = inlineformset_factory(
    ChecklistSection, ChecklistSubsection,
    fields=["number", "name", "order"],
    extra=0, can_delete=True,
)

ItemFormSet = inlineformset_factory(
    ChecklistSubsection, ChecklistItem,
    fields=["number", "description", "order"],
    extra=0, can_delete=True,
    widgets={"description": forms.Textarea(attrs={"rows": 2})},
)


@login_required
def checklist_template_edit(request, pk):
    if not _require_admin_role(request):
        return redirect("dashboard")

    template = get_object_or_404(ChecklistTemplate, pk=pk)

    if request.method == "POST":
        meta_form = ChecklistTemplateMetaForm(request.POST, instance=template)
        formset = SectionFormSet(request.POST, instance=template)
        if meta_form.is_valid() and formset.is_valid():
            meta_form.save()
            formset.save()
            messages.success(request, "Zapisano zmiany w checkliście.")
            return redirect("checklist_template_edit", pk=template.pk)
        messages.error(request, "Formularz zawiera błędy - sprawdź pola poniżej.")
    else:
        meta_form = ChecklistTemplateMetaForm(instance=template)
        formset = SectionFormSet(instance=template)

    return render(request, "audits/checklist_template_edit.html", {
        "template_obj": template,
        "meta_form": meta_form,
        "formset": formset,
    })


@login_required
def checklist_section_edit(request, pk):
    if not _require_admin_role(request):
        return redirect("dashboard")

    section = get_object_or_404(ChecklistSection, pk=pk)

    if request.method == "POST":
        formset = SubsectionFormSet(request.POST, instance=section)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Zapisano zmiany w podsekcjach.")
            return redirect("checklist_section_edit", pk=section.pk)
        messages.error(request, "Formularz zawiera błędy - sprawdź pola poniżej.")
    else:
        formset = SubsectionFormSet(instance=section)

    return render(request, "audits/checklist_section_edit.html", {
        "section": section,
        "formset": formset,
    })


@login_required
def checklist_subsection_edit(request, pk):
    if not _require_admin_role(request):
        return redirect("dashboard")

    subsection = get_object_or_404(ChecklistSubsection, pk=pk)

    if request.method == "POST":
        formset = ItemFormSet(request.POST, instance=subsection)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Zapisano zmiany w punktach kontrolnych.")
            return redirect("checklist_subsection_edit", pk=subsection.pk)
        messages.error(request, "Formularz zawiera błędy - sprawdź pola poniżej.")
    else:
        formset = ItemFormSet(instance=subsection)

    return render(request, "audits/checklist_subsection_edit.html", {
        "subsection": subsection,
        "formset": formset,
    })
