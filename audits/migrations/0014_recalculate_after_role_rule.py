from datetime import datetime, timedelta, timezone

from django.db import migrations

# Moment wdrożenia błędnej reguły punktacji ("przedstawiciele obszaru"). Inspekcje zapisane
# od tego czasu mają punkty policzone błędnie, więc są przeliczane regułą oparta na roli.
# Inspekcje zapisane wcześniej NIE są ruszane (zachowują swój historyczny wynik).
CUTOFF = datetime(2026, 10, 27, 10, 22, 54, tzinfo=timezone(timedelta(hours=1)))
NO_DEDUCTION_ROLE = "UZYTKOWNIK_OBSZARU"


def deducts(person):
    return person is None or person.role != NO_DEDUCTION_ROLE


def recalculate(apps, schema_editor):
    Inspection = apps.get_model("audits", "Inspection")
    Section = apps.get_model("audits", "ChecklistSection")
    SectionResult = apps.get_model("audits", "InspectionSectionResult")
    NonConformity = apps.get_model("audits", "NonConformity")

    for inspection in Inspection.objects.filter(updated_at__gte=CUTOFF):
        for section in Section.objects.filter(template_id=inspection.template_id):
            ncs = NonConformity.objects.filter(
                inspection=inspection, is_extra=False, checklist_item__subsection__section=section,
            ).select_related("checklist_item", "responsible_person")
            weight = sum(nc.checklist_item.penalty_weight for nc in ncs if deducts(nc.responsible_person))
            SectionResult.objects.update_or_create(
                inspection=inspection, section=section,
                defaults={"points_awarded": max(0, section.max_points - weight)},
            )
        extras = NonConformity.objects.filter(inspection=inspection, is_extra=True).select_related(
            "checklist_item", "responsible_person",
        )
        extra_penalty = sum(
            (nc.checklist_item.penalty_weight if nc.checklist_item_id else 1)
            for nc in extras if deducts(nc.responsible_person)
        )
        # update() zamiast save(), żeby nie zmieniać updated_at
        Inspection.objects.filter(pk=inspection.pk).update(extra_penalty=extra_penalty)


class Migration(migrations.Migration):

    dependencies = [
        ('audits', '0013_mix_form'),
    ]

    operations = [
        migrations.RunPython(recalculate, migrations.RunPython.noop),
    ]
