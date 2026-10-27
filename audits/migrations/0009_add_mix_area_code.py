from django.db import migrations, models


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
    ]
