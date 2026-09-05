"""Das Ereignis -- die einzige Wahrheit im Modell (SPEC 4).

Alles andere wird daraus abgeleitet: die Historie ist die Liste der Ereignisse,
die Faelligkeit ist juengstes Ereignis + Intervall. Es gibt keinen gespeicherten
Faelligkeitszustand, der veralten koennte.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .bestand import Aufgabe, Bereich
from .katalog import Taetigkeit


class Ereignis(models.Model):
    bereich = models.ForeignKey(
        Bereich, on_delete=models.PROTECT, related_name="ereignisse", verbose_name=_("Bereich")
    )
    aufgabe = models.ForeignKey(
        Aufgabe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ereignisse",
        verbose_name=_("Aufgabe"),
        help_text=_("Leer lassen bei einmaligen Vorgängen."),
    )
    taetigkeit = models.ForeignKey(
        Taetigkeit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ereignisse",
        verbose_name=_("Tätigkeit"),
    )
    beschreibung = models.CharField(
        _("Beschreibung"),
        max_length=200,
        blank=True,
        help_text=_("Nur nötig, wenn keine Tätigkeit aus dem Katalog passt."),
    )

    datum = models.DateField(_("Datum"), db_index=True)
    kosten = models.DecimalField(_("Kosten"), max_digits=10, decimal_places=2, null=True, blank=True)
    ausgefuehrt_von = models.CharField(_("ausgeführt von"), max_length=120, blank=True)
    notiz = models.TextField(
        _("Notiz"), blank=True, help_text=_('Material, Farbton, Menge – z. B. "RAL 7016, 12 l".')
    )

    erfasst_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ereignisse",
        verbose_name=_("erfasst von"),
    )
    erfasst_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Ereignis")
        verbose_name_plural = _("Ereignisse")
        ordering = ["-datum", "-erfasst_am"]
        indexes = [models.Index(fields=["aufgabe", "-datum"], name="ereignis_aufgabe_datum")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(taetigkeit__isnull=False) | ~models.Q(beschreibung=""),
                name="ereignis_braucht_taetigkeit_oder_beschreibung",
            )
        ]

    def __str__(self) -> str:
        return f"{self.datum}: {self.bezeichnung} ({self.bereich})"

    @property
    def bezeichnung(self) -> str:
        """Was wurde gemacht -- Katalogbegriff bevorzugt, sonst Freitext."""
        if self.taetigkeit_id:
            return self.taetigkeit.name
        return self.beschreibung

    def _ableiten(self):
        """Ergaenzt, was sich aus der Aufgabe von selbst ergibt.

        Laeuft vor der Validierung, nicht erst beim Speichern: Sonst wuerde ein
        Formular, das nur die Aufgabe kennt (Abhak-Seite, SPEC 6), an der
        Pflichtfeldpruefung fuer den Bereich scheitern.
        """
        if not self.aufgabe_id:
            return
        if not self.bereich_id:
            self.bereich_id = self.aufgabe.bereich_id
        if not self.taetigkeit_id:
            self.taetigkeit_id = self.aufgabe.taetigkeit_id

    def full_clean(self, *args, **kwargs):
        self._ableiten()
        super().full_clean(*args, **kwargs)

    def clean(self):
        if not self.taetigkeit_id and not self.beschreibung.strip():
            raise ValidationError(
                _("Bitte eine Tätigkeit aus dem Katalog wählen oder eine Beschreibung eintragen.")
            )
        if self.aufgabe_id and self.bereich_id and self.aufgabe.bereich_id != self.bereich_id:
            raise ValidationError({"aufgabe": _("Die Aufgabe gehört zu einem anderen Bereich.")})

    def save(self, *args, **kwargs):
        self._ableiten()
        super().save(*args, **kwargs)
