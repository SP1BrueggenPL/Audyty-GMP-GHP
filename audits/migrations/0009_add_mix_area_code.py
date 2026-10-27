from django.db import migrations, models


def create_mix_template(apps, schema_editor):
    """Tworzy formularz Miksowanie jako kopię aktualnego formularza WCE/WPP (te same
    zakresy, podsekcje, punkty, limity punktów i wagi). Jeśli nie ma jeszcze żadnego
    formularza WCE/WPP (świeża baza) albo formularz MIX już istnieje - nic nie robi.
    Numer dokumentu i nazwę wersji uzupełnia administrator w edytorze checklisty."""
    Template = apps.get_model("audits", "ChecklistTemplate")
    Section = apps.get_model("audits", "ChecklistSection")
    Subsection = apps.get_model("audits", "ChecklistSubsection")
    Item = apps.get_model("audits", "ChecklistItem")

    if Template.objects.filter(area_code="MIX").exists():
        return
    source = Template.objects.filter(area_code="WCE_WPP", is_active=True).order_by("-created_at").first()
    if source is None:
        return

    new = Template.objects.create(
        area_code="MIX",
        name="Inspekcja GMP/GHP - MIKSOWANIE",
        document_code="do uzupełnienia",
        version_note="kopia formularza WCE/WPP - uzupełnij numer dokumentu",
        is_active=True,
    )
    for section in Section.objects.filter(template=source).order_by("order"):
        new_section = Section.objects.create(
            template=new, order=section.order, label=section.label, name=section.name,
            max_points=section.max_points,
        )
        for sub in Subsection.objects.filter(section=section).order_by("order"):
            new_sub = Subsection.objects.create(
                section=new_section, order=sub.order, number=sub.number, name=sub.name,
            )
            for item in Item.objects.filter(subsection=sub).order_by("order"):
                Item.objects.create(
                    subsection=new_sub, order=item.order, number=item.number,
                    description=item.description, penalty_weight=item.penalty_weight,
                )


class Migration(migrations.Migration):

    dependencies = [
        ('audits', '0008_checklistitem_penalty_weight'),
    ]

    operations = [
        migrations.AlterField(
            model_name='checklisttemplate',
            name='area_code',
            field=models.CharField(choices=[('WCE_WPP', 'WCE/WPP - Produkcja i Pakownia'), ('MIX', 'MIX - Miksowanie'), ('WLS', 'WLS - Magazyn'), ('WED', 'WED - Dział techniczny')], max_length=10),
        ),
        migrations.RunPython(create_mix_template, migrations.RunPython.noop),
    ]
