"""Kalenderschlüssel je Konto (SPEC 7).

Dreistufig, wie die Django-Dokumentation es für eindeutige Felder mit
Zufallsvorgabe vorsieht: erst hinzufügen, dann je Zeile einen eigenen Wert
setzen, dann die Eindeutigkeit erzwingen. Eine einstufige Migration würde allen
Bestandszeilen denselben Schlüssel geben.
"""

from django.db import migrations, models

import wartung.models.benutzer


def schluessel_vergeben(apps, schema_editor):
    Benutzer = apps.get_model("wartung", "Benutzer")
    for benutzer in Benutzer.objects.all():
        benutzer.kalender_schluessel = wartung.models.benutzer.neuer_kalenderschluessel()
        benutzer.save(update_fields=["kalender_schluessel"])


class Migration(migrations.Migration):
    dependencies = [("wartung", "0004_zugangsmarke")]

    operations = [
        migrations.AddField(
            model_name="benutzer",
            name="kalender_schluessel",
            field=models.CharField(
                default=wartung.models.benutzer.neuer_kalenderschluessel,
                max_length=43,
                verbose_name="Kalenderschlüssel",
            ),
        ),
        migrations.RunPython(schluessel_vergeben, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="benutzer",
            name="kalender_schluessel",
            field=models.CharField(
                default=wartung.models.benutzer.neuer_kalenderschluessel,
                max_length=43,
                unique=True,
                verbose_name="Kalenderschlüssel",
            ),
        ),
    ]
