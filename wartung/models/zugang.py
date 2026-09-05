"""Zugangsmarken fuer Magic Link und Ein-Klick-Abhaken (SPEC 2, SPEC 6, SPEC 8).

Zwei getrennte Arten mit unterschiedlicher Reichweite: Die Anmeldemarke
erzeugt eine Sitzung, die Abhakmarke nicht. Wer eine Abhakmarke abfaengt, kann
genau eine Aufgabe abhaken und sonst nichts.

Gespeichert wird nur der Hash. Ein Blick in die Datenbank -- oder eine Sicherung
davon -- ergibt keine benutzbaren Links.
"""

import datetime as dt
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: Anmeldelinks sollen kurz leben; man klickt sie binnen Minuten.
GUELTIGKEIT_ANMELDUNG = dt.timedelta(hours=1)
#: Abhaklinks stehen in der Wochenmail und muessen die Woche ueberdauern.
GUELTIGKEIT_ERLEDIGUNG = dt.timedelta(days=10)


class Zweck(models.TextChoices):
    ANMELDUNG = "anmeldung", _("Anmeldung")
    ERLEDIGUNG = "erledigung", _("Erledigung")


def _hashen(roh: str) -> str:
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


class ZugangsmarkenManager(models.Manager):
    def anlegen(self, zweck, benutzer, aufgabe=None, gueltigkeit=None):
        """Legt eine Marke an und gibt sie samt Rohwert zurueck.

        Der Rohwert existiert nur in diesem Augenblick und in der Mail --
        gespeichert wird ausschliesslich sein Hash.
        """
        roh = secrets.token_urlsafe(32)
        if gueltigkeit is None:
            gueltigkeit = (
                GUELTIGKEIT_ERLEDIGUNG if zweck == Zweck.ERLEDIGUNG else GUELTIGKEIT_ANMELDUNG
            )
        marke = self.create(
            schluessel_hash=_hashen(roh),
            zweck=zweck,
            benutzer=benutzer,
            aufgabe=aufgabe,
            gueltig_bis=timezone.now() + gueltigkeit,
        )
        return marke, roh

    def einloesen(self, roh: str, zweck):
        """Prueft eine Marke und verbraucht sie. Gibt None zurueck, wenn sie
        nicht taugt -- abgelaufen, schon benutzt, falscher Zweck, erfunden."""
        if not roh:
            return None
        jetzt = timezone.now()
        marke = self.filter(
            schluessel_hash=_hashen(roh),
            zweck=zweck,
            verbraucht_am__isnull=True,
            gueltig_bis__gt=jetzt,
        ).select_related("benutzer", "aufgabe__bereich__objekt", "aufgabe__taetigkeit").first()
        if marke is None:
            return None
        marke.verbraucht_am = jetzt
        marke.save(update_fields=["verbraucht_am"])
        return marke

    def pruefen(self, roh: str, zweck):
        """Wie einloesen, aber ohne zu verbrauchen -- fuer das Anzeigen des
        Formulars. Ein blosser Aufruf darf nichts veraendern (SPEC 6)."""
        if not roh:
            return None
        return (
            self.filter(
                schluessel_hash=_hashen(roh),
                zweck=zweck,
                verbraucht_am__isnull=True,
                gueltig_bis__gt=timezone.now(),
            )
            .select_related("benutzer", "aufgabe__bereich__objekt", "aufgabe__taetigkeit")
            .first()
        )


class Zugangsmarke(models.Model):
    schluessel_hash = models.CharField(max_length=64, unique=True, db_index=True)
    zweck = models.CharField(max_length=12, choices=Zweck.choices)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="marken"
    )
    aufgabe = models.ForeignKey(
        "wartung.Aufgabe", on_delete=models.CASCADE, null=True, blank=True, related_name="marken"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    gueltig_bis = models.DateTimeField()
    verbraucht_am = models.DateTimeField(null=True, blank=True)

    objects = ZugangsmarkenManager()

    class Meta:
        verbose_name = _("Zugangsmarke")
        verbose_name_plural = _("Zugangsmarken")
        ordering = ["-erstellt_am"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(zweck=Zweck.ERLEDIGUNG) | models.Q(aufgabe__isnull=False),
                name="abhakmarke_braucht_aufgabe",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_zweck_display()} für {self.benutzer}"
