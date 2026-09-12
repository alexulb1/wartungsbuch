"""Die Bereichsbezeichnung wird dreisprachig.

Der bisherige Freitext ist der deutsche: umbenennen statt neu anlegen, damit
die vorhandenen Bezeichnungen erhalten bleiben. Die Eindeutigkeit je Objekt
haengt weiter am deutschen Text.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wartung", "0009_ereignis_absendekennung")]

    operations = [
        migrations.RemoveConstraint(
            model_name="bereich",
            name="bereich_je_objekt_eindeutig",
        ),
        migrations.RenameField(
            model_name="bereich",
            old_name="bezeichnung",
            new_name="bezeichnung_de",
        ),
        migrations.AlterField(
            model_name="bereich",
            name="bezeichnung_de",
            field=models.CharField(
                blank=True,
                help_text='Zusatz zur Unterscheidung, z. B. "Nord" oder "OG".',
                max_length=80,
                verbose_name="Bezeichnung (Deutsch)",
            ),
        ),
        migrations.AddField(
            model_name="bereich",
            name="bezeichnung_en",
            field=models.CharField(
                blank=True, max_length=80, verbose_name="Bezeichnung (Englisch)"
            ),
        ),
        migrations.AddField(
            model_name="bereich",
            name="bezeichnung_sv",
            field=models.CharField(
                blank=True, max_length=80, verbose_name="Bezeichnung (Schwedisch)"
            ),
        ),
        migrations.AlterModelOptions(
            name="bereich",
            options={
                "ordering": ["objekt__name", "typ__sortierung", "bezeichnung_de"],
                "verbose_name": "Bereich",
                "verbose_name_plural": "Bereiche",
            },
        ),
        migrations.AddConstraint(
            model_name="bereich",
            constraint=models.UniqueConstraint(
                fields=("objekt", "typ", "bezeichnung_de"),
                name="bereich_je_objekt_eindeutig",
            ),
        ),
    ]
