"""Einfacher Zeitplaner fuer den Dauerbetrieb im Container (SPEC 9).

    python manage.py planer

Klopft stuendlich an und ueberlaesst die Entscheidung den Befehlen selbst. Das
ist Absicht: Ein Zeitplaner, der auf die Minute genau ausloest, verliert seine
Aufgabe, wenn der Rechner in diesem Moment gerade neu startet. Hier geht
nichts verloren -- und doppelt passiert trotzdem nichts, weil die Befehle
idempotent sind.

Ein Fehler in einem Schritt beendet den Planer nicht. Ueber zehn Jahre wird
irgendwann etwas schiefgehen; ein Planer, der daran stirbt, bleibt fuer immer
stehen, ohne dass es jemandem auffaellt.
"""

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Führt Wochenmail, Aufräumen und Sicherung wiederkehrend aus."

    def add_arguments(self, parser):
        parser.add_argument("--intervall", type=int, default=3600, help="Sekunden zwischen Läufen.")
        parser.add_argument("--einmal", action="store_true", help="Nur ein Durchlauf.")
        parser.add_argument("--jetzt", help="Abweichender Zeitpunkt (für Proben).")

    def handle(self, *args, **optionen):
        while True:
            self._durchlauf(optionen)
            if optionen["einmal"]:
                return
            time.sleep(optionen["intervall"])

    def _durchlauf(self, optionen):
        for name, schritt in [
            ("Wochenmail", lambda: self.wochenmail(optionen)),
            ("Marken aufräumen", self.marken_aufraeumen),
            ("Anhänge aufräumen", self.anhaenge_aufraeumen),
            ("Sicherung", self.sicherung),
        ]:
            try:
                schritt()
            except Exception as fehler:  # noqa: BLE001 -- der Planer muss weiterlaufen
                self.stderr.write(self.style.ERROR(f"{name} fehlgeschlagen: {fehler}"))

    def wochenmail(self, optionen):
        call_command(
            "wochenmail", geplant=True, jetzt=optionen.get("jetzt"), stdout=self.stdout
        )

    def marken_aufraeumen(self):
        call_command("marken_aufraeumen", stdout=self.stdout)

    def anhaenge_aufraeumen(self):
        call_command("anhaenge_aufraeumen", stdout=self.stdout)

    def sicherung(self):
        call_command("sicherung", taeglich=True, stdout=self.stdout)
