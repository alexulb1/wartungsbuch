"""Der Bestand: Objekt -> Bereich -> Aufgabe (SPEC 4)."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .basis import Einheit, Modus
from .katalog import BereichsTyp, ObjektTyp, Taetigkeit



class Objekt(models.Model):
    """Ein Haus, eine Wohnung, ein Sommerhaus.

    Der Name ist Freitext und wird nicht uebersetzt -- Eigennamen uebersetzt
    man nicht (SPEC 3). Der Typ dagegen kommt aus dem Katalog.
    """

    name = models.CharField(_("Name"), max_length=120)
    typ = models.ForeignKey(
        ObjektTyp, on_delete=models.PROTECT, related_name="objekte", verbose_name=_("Typ")
    )
    aktiv_ab_monat = models.PositiveSmallIntegerField(
        _("Ruhezeit: aktiv ab Monat"),
        null=True,
        blank=True,
        help_text=_("Leer lassen fuer ganzjaehrig. Beispiel Sommerhaus: 4 bis 10."),
    )
    aktiv_bis_monat = models.PositiveSmallIntegerField(
        _("Ruhezeit: aktiv bis Monat"), null=True, blank=True
    )
    notiz = models.TextField(_("Notiz"), blank=True)
    angelegt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Objekt")
        verbose_name_plural = _("Objekte")
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(aktiv_ab_monat__isnull=True)
                | models.Q(aktiv_ab_monat__gte=1, aktiv_ab_monat__lte=12),
                name="objekt_aktiv_ab_1_bis_12",
            ),
            models.CheckConstraint(
                condition=models.Q(aktiv_bis_monat__isnull=True)
                | models.Q(aktiv_bis_monat__gte=1, aktiv_bis_monat__lte=12),
                name="objekt_aktiv_bis_1_bis_12",
            ),
            models.CheckConstraint(
                condition=models.Q(aktiv_ab_monat__isnull=True, aktiv_bis_monat__isnull=True)
                | models.Q(aktiv_ab_monat__isnull=False, aktiv_bis_monat__isnull=False),
                name="objekt_ruhezeit_vollstaendig",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def hat_ruhezeit(self) -> bool:
        return self.aktiv_ab_monat is not None and self.aktiv_bis_monat is not None

    def meldet_im_monat(self, monat: int) -> bool:
        """Erscheint dieses Objekt in der Wochenmail dieses Monats? (SPEC 6)

        Die Ruhezeit unterdrueckt nur die Meldung -- Faelligkeiten laufen im
        Hintergrund weiter und sind in der App jederzeit sichtbar.
        """
        if not self.hat_ruhezeit:
            return True
        ab, bis = self.aktiv_ab_monat, self.aktiv_bis_monat
        if ab <= bis:
            return ab <= monat <= bis
        return monat >= ab or monat <= bis  # Zeitraum ueber den Jahreswechsel


class Bereich(models.Model):
    """Ein Bauteil oder Abschnitt eines Objekts.

    Der Typ kommt aus dem Katalog ("Fassade"), die Bezeichnung unterscheidet
    gleichartige Bereiche voneinander ("Nord", "Sued", "OG").
    """

    objekt = models.ForeignKey(
        Objekt, on_delete=models.CASCADE, related_name="bereiche", verbose_name=_("Objekt")
    )
    typ = models.ForeignKey(
        BereichsTyp, on_delete=models.PROTECT, related_name="bereiche", verbose_name=_("Typ")
    )
    bezeichnung = models.CharField(
        _("Bezeichnung"),
        max_length=80,
        blank=True,
        help_text=_('Zusatz zur Unterscheidung, z. B. "Nord" oder "OG".'),
    )
    notiz = models.TextField(_("Notiz"), blank=True)

    class Meta:
        verbose_name = _("Bereich")
        verbose_name_plural = _("Bereiche")
        ordering = ["objekt__name", "typ__sortierung", "bezeichnung"]
        constraints = [
            models.UniqueConstraint(
                fields=["objekt", "typ", "bezeichnung"], name="bereich_je_objekt_eindeutig"
            )
        ]

    def __str__(self) -> str:
        return f"{self.typ.name} {self.bezeichnung}".strip()


class Aufgabe(models.Model):
    """Eine wiederkehrende Taetigkeit an einem Bereich.

    Die Faelligkeit wird nicht hier gespeichert, sondern aus dem juengsten
    Ereignis berechnet (SPEC 4). Dieses Modell haelt nur die Regel.
    """

    bereich = models.ForeignKey(
        Bereich,
        on_delete=models.CASCADE,
        related_name="aufgaben",
        verbose_name=_("Bereich"),
    )
    taetigkeit = models.ForeignKey(
        Taetigkeit, on_delete=models.PROTECT, related_name="aufgaben", verbose_name=_("Taetigkeit")
    )
    intervall_wert = models.PositiveIntegerField(_("Intervall"))
    intervall_einheit = models.CharField(_("Einheit"), max_length=10, choices=Einheit.choices)
    modus = models.CharField(
        _("Modus"), max_length=10, choices=Modus.choices, default=Modus.RELATIV
    )
    kalender_monat = models.PositiveSmallIntegerField(
        _("Monat"), null=True, blank=True, help_text=_("Nur beim festen Kalenderrhythmus.")
    )
    kalender_tag = models.PositiveSmallIntegerField(
        _("Tag"), null=True, blank=True, help_text=_("Nur beim festen Kalenderrhythmus.")
    )
    aktiv = models.BooleanField(_("aktiv"), default=True)
    notiz = models.TextField(_("Notiz"), blank=True)

    class Meta:
        verbose_name = _("Aufgabe")
        verbose_name_plural = _("Aufgaben")
        ordering = ["bereich__objekt__name", "bereich__typ__sortierung", "taetigkeit__sortierung"]
        constraints = [
            models.UniqueConstraint(
                fields=["bereich", "taetigkeit"], name="aufgabe_je_bereich_eindeutig"
            ),
            models.CheckConstraint(condition=models.Q(intervall_wert__gte=1), name="aufgabe_intervall_positiv"),
            models.CheckConstraint(
                condition=~models.Q(modus=Modus.KALENDER) | models.Q(kalender_monat__isnull=False),
                name="aufgabe_kalendermodus_braucht_monat",
            ),
            models.CheckConstraint(
                # Ein Monatsintervall und ein fester Monat widersprechen
                # einander: Der Kalendermodus ist ein jaehrlich wiederkehrender
                # Termin, moeglicherweise nur alle N Jahre.
                condition=~models.Q(modus=Modus.KALENDER)
                | models.Q(intervall_einheit=Einheit.JAHRE),
                name="aufgabe_kalendermodus_braucht_jahre",
            ),
            models.CheckConstraint(
                condition=models.Q(kalender_monat__isnull=True)
                | models.Q(kalender_monat__gte=1, kalender_monat__lte=12),
                name="aufgabe_kalendermonat_1_bis_12",
            ),
            models.CheckConstraint(
                condition=models.Q(kalender_tag__isnull=True)
                | models.Q(kalender_tag__gte=1, kalender_tag__lte=31),
                name="aufgabe_kalendertag_1_bis_31",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.taetigkeit.name} ({self.bereich})"

    def clean(self):
        if self.modus == Modus.KALENDER and not self.kalender_monat:
            raise ValidationError(
                {"kalender_monat": _("Beim festen Kalenderrhythmus wird ein Monat gebraucht.")}
            )
        if self.modus == Modus.KALENDER and self.intervall_einheit != Einheit.JAHRE:
            raise ValidationError(
                {
                    "intervall_einheit": _(
                        "Der feste Kalenderrhythmus zaehlt in Jahren. Fuer kuerzere "
                        "Abstaende bitte den Modus \"relativ zur letzten Erledigung\" waehlen."
                    )
                }
            )
