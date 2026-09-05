"""Gemeinsame Bausteine des Datenmodells."""

from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class Sprache(models.TextChoices):
    DEUTSCH = "de", _("Deutsch")
    ENGLISCH = "en", _("Englisch")
    SCHWEDISCH = "sv", _("Schwedisch")


class Einheit(models.TextChoices):
    """Zeiteinheit eines Wartungsintervalls."""

    TAGE = "tage", _("Tage")
    MONATE = "monate", _("Monate")
    JAHRE = "jahre", _("Jahre")


class Modus(models.TextChoices):
    """Wie die naechste Faelligkeit bestimmt wird (SPEC 5)."""

    RELATIV = "relativ", _("Relativ zur letzten Erledigung")
    KALENDER = "kalender", _("Fester Kalenderrhythmus")


class UebersetzterName(models.Model):
    """Katalogdaten tragen ihre Bezeichnung in allen drei Sprachen (SPEC 3).

    Fehlt eine Uebersetzung, wird auf Deutsch zurueckgefallen -- die Oberflaeche
    zeigt dann lieber einen deutschen Begriff als eine leere Zelle.
    """

    name_de = models.CharField(_("Bezeichnung (Deutsch)"), max_length=120)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=120, blank=True)
    name_sv = models.CharField(_("Bezeichnung (Schwedisch)"), max_length=120, blank=True)

    class Meta:
        abstract = True

    def name_in(self, sprache: str | None) -> str:
        code = (sprache or Sprache.DEUTSCH)[:2]
        return getattr(self, f"name_{code}", "") or self.name_de

    @property
    def name(self) -> str:
        """Bezeichnung in der aktuell aktiven Sprache."""
        return self.name_in(get_language())

    def __str__(self) -> str:
        return self.name
