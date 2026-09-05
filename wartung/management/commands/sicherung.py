"""Schreibt eine Datensicherung als JSON (SPEC 10.4).

    python manage.py sicherung --taeglich

Bewusst JSON statt pg_dump: Der Bestand ist klein, und eine JSON-Datei laesst
sich auch dann noch lesen, wenn es diese Anwendung oder diese Postgres-Fassung
nicht mehr gibt. Bei einem Wartungsbuch, das zehn Jahre halten soll, ist
Lesbarkeit mehr wert als Wiederherstellungsgeschwindigkeit.

Die Dateien liegen in einem Verzeichnis, das die Sicherung des NAS mitnimmt.
"""

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

#: Marken sind fluechtig und haetten in einer Sicherung nur Angriffsflaeche.
AUSGENOMMEN = ["wartung.zugangsmarke", "sessions.session", "admin.logentry", "contenttypes"]


class Command(BaseCommand):
    help = "Schreibt eine JSON-Sicherung aller Daten."

    def add_arguments(self, parser):
        parser.add_argument("--verzeichnis", default=None)
        parser.add_argument("--behalten", type=int, default=30, help="Wie viele Stände bleiben.")
        parser.add_argument(
            "--taeglich",
            action="store_true",
            help="Überspringen, wenn für heute schon eine Sicherung liegt.",
        )

    def handle(self, *args, **optionen):
        ordner = Path(optionen["verzeichnis"] or settings.SICHERUNGS_VERZEICHNIS)
        ordner.mkdir(parents=True, exist_ok=True)

        heute = timezone.localdate()
        ziel = ordner / f"wartungsbuch-{heute.isoformat()}.json"

        if optionen["taeglich"] and ziel.exists():
            self.stdout.write(f"Für heute liegt schon eine Sicherung: {ziel.name}")
            self._aufraeumen(ordner, optionen["behalten"])
            return

        with ziel.open("w", encoding="utf-8") as datei:
            call_command(
                "dumpdata",
                exclude=AUSGENOMMEN,
                natural_foreign=True,
                indent=1,
                stdout=datei,
            )
        self.stdout.write(self.style.SUCCESS(f"Gesichert: {ziel} ({ziel.stat().st_size} Bytes)"))
        self._aufraeumen(ordner, optionen["behalten"])

    def _aufraeumen(self, ordner: Path, behalten: int) -> None:
        staende = sorted(ordner.glob("wartungsbuch-*.json"))
        for alt in staende[: max(0, len(staende) - behalten)]:
            alt.unlink()
            self.stdout.write(f"Entfernt: {alt.name}")
