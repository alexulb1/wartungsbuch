"""Leert den Papierkorb der Anhänge.

    python manage.py anhaenge_aufraeumen

Gelöschte Anhänge liegen 30 Tage in geloescht/, damit ein Versehen zurückholbar
bleibt. Danach sind sie Ballast -- und je weniger liegt, desto weniger gibt es
zu verlieren. Dieselbe Überlegung wie bei den Zugangsmarken.
"""

import datetime as dt
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from wartung.models.anhang import PAPIERKORB

SCHONFRIST = dt.timedelta(days=30)


class Command(BaseCommand):
    help = "Löscht Anhänge im Papierkorb, die älter als 30 Tage sind."

    def handle(self, *args, **optionen):
        korb = Path(settings.MEDIA_ROOT) / PAPIERKORB
        if not korb.is_dir():
            self.stdout.write("Kein Papierkorb vorhanden.")
            return

        grenze = time.time() - SCHONFRIST.total_seconds()
        entfernt = 0
        for datei in korb.iterdir():
            if datei.is_file() and datei.stat().st_mtime < grenze:
                datei.unlink()
                entfernt += 1
        self.stdout.write(self.style.SUCCESS(f"{entfernt} Anhang/Anhänge entfernt."))
