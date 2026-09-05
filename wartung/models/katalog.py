"""Katalogdaten -- die dreisprachig gepflegte Auswahlliste (SPEC 3, SPEC 7).

Objekttypen, Bereichstypen und Taetigkeiten werden ausgewaehlt statt getippt.
Das ist die Voraussetzung fuer Mehrsprachigkeit und macht Auswertungen ueber
mehrere Objekte hinweg ueberhaupt erst moeglich.
"""

from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from .basis import Einheit, Modus, Sprache, UebersetzterName


class ObjektTyp(UebersetzterName):
    """Haus, Sommerhaus, Wohnung ..."""

    schluessel = models.SlugField(_("Schlüssel"), unique=True)
    sortierung = models.PositiveSmallIntegerField(_("Sortierung"), default=100)

    class Meta:
        verbose_name = _("Objekttyp")
        verbose_name_plural = _("Objekttypen")
        ordering = ["sortierung", "name_de"]


class BereichsTyp(UebersetzterName):
    """Waermepumpe, Fassade, Klimageraet ..."""

    schluessel = models.SlugField(_("Schlüssel"), unique=True)
    sortierung = models.PositiveSmallIntegerField(_("Sortierung"), default=100)

    class Meta:
        verbose_name = _("Bereichstyp")
        verbose_name_plural = _("Bereichstypen")
        ordering = ["sortierung", "name_de"]


class Taetigkeit(UebersetzterName):
    """Eine Wartungstaetigkeit samt ueblichem Intervall.

    Der Hinweistext ist der eigentliche Wert des Katalogs: Er beantwortet
    "woran haette ich denken muessen" (SPEC 7).
    """

    schluessel = models.SlugField(_("Schlüssel"), unique=True)
    bereichs_typen = models.ManyToManyField(
        BereichsTyp,
        related_name="taetigkeiten",
        verbose_name=_("passt zu Bereichstypen"),
        blank=True,
    )

    hinweis_de = models.TextField(_("Hinweis (Deutsch)"), blank=True)
    hinweis_en = models.TextField(_("Hinweis (Englisch)"), blank=True)
    hinweis_sv = models.TextField(_("Hinweis (Schwedisch)"), blank=True)

    standard_intervall_wert = models.PositiveIntegerField(
        _("übliches Intervall"), null=True, blank=True
    )
    standard_intervall_einheit = models.CharField(
        _("Einheit"), max_length=10, choices=Einheit.choices, blank=True
    )
    standard_modus = models.CharField(
        _("Modus"), max_length=10, choices=Modus.choices, default=Modus.RELATIV
    )
    standard_kalender_monat = models.PositiveSmallIntegerField(
        _("Monat im Kalenderrhythmus"), null=True, blank=True
    )
    sortierung = models.PositiveSmallIntegerField(_("Sortierung"), default=100)

    class Meta:
        verbose_name = _("Tätigkeit")
        verbose_name_plural = _("Tätigkeiten")
        ordering = ["sortierung", "name_de"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(standard_kalender_monat__isnull=True)
                | models.Q(standard_kalender_monat__gte=1, standard_kalender_monat__lte=12),
                name="taetigkeit_kalendermonat_1_bis_12",
            ),
        ]

    @property
    def hinweis(self) -> str:
        code = (get_language() or Sprache.DEUTSCH)[:2]
        return getattr(self, f"hinweis_{code}", "") or self.hinweis_de
