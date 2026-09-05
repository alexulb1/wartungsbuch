"""Entfernt verbrauchte und abgelaufene Zugangsmarken.

    python manage.py marken_aufraeumen

Sinnvoll als woechentliche Aufgabe neben der Wochenmail. Marken, die nichts
mehr oeffnen, sind Ballast -- und je weniger davon liegt, desto weniger gibt
es zu verlieren.
"""

import datetime as dt

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from wartung.models import Zugangsmarke

#: Verbrauchtes und Abgelaufenes wird so lange aufgehoben, dass sich ein
#: "der Link ging nicht" noch nachvollziehen laesst.
SCHONFRIST = dt.timedelta(days=30)


class Command(BaseCommand):
    help = "Löscht verbrauchte und abgelaufene Zugangsmarken."

    def handle(self, *args, **optionen):
        grenze = timezone.now() - SCHONFRIST
        alt = Zugangsmarke.objects.filter(
            Q(verbraucht_am__lt=grenze) | Q(gueltig_bis__lt=grenze)
        )
        anzahl = alt.count()
        alt.delete()
        self.stdout.write(self.style.SUCCESS(f"{anzahl} Marke(n) entfernt."))
