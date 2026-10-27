from django.db import migrations


def remove_wrong_mix_clone(apps, schema_editor):
    """Wcześniejsza wersja migracji 0009 utworzyła formularz MIX jako kopię Pakowni
    (z numerem dokumentu "do uzupełnienia"). To była pomyłka - MIX ma własny, znacznie
    krótszy formularz importowany z Excela. Usuwa tę kopię; jeśli ma już zapisane
    inspekcje, tylko ją dezaktywuje (inspekcje wskazują na szablon)."""
    Template = apps.get_model("audits", "ChecklistTemplate")
    Inspection = apps.get_model("audits", "Inspection")
    for template in Template.objects.filter(area_code="MIX", document_code="do uzupełnienia"):
        if Inspection.objects.filter(template=template).exists():
            template.is_active = False
            template.save(update_fields=["is_active"])
        else:
            template.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('audits', '0009_add_mix_area_code'),
    ]

    operations = [
        migrations.RunPython(remove_wrong_mix_clone, migrations.RunPython.noop),
    ]
