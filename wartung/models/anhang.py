"""Anhänge: Fotos, Belege und Bauteil-Unterlagen.

Aufgebaut wie das Ereignis selbst: Der Bereich ist Pflicht, der Bezug darüber
optional. Aus dem Bereich folgt das Objekt und damit die Berechtigung -- ein
Weg, keine Fallunterscheidung.

Die Dateien liegen unter selbsterklärenden Namen im Dateisystem, damit sie in
zehn Jahren auch ohne diese Anwendung lesbar sind. Das war der Grund, sie nicht
in die Datenbank zu legen.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

#: Größer als ein Handyfoto und eine gescannte mehrseitige Rechnung, kleiner
#: als ein versehentlich hochgeladenes Video.
HOECHSTGROESSE = 25 * 1024 * 1024

#: Je enger die Liste, desto weniger gelangt über diesen Weg auf den Speicher.
ERLAUBTE_TYPEN = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "application/pdf": ".pdf",
}

#: Wohin Gelöschtes wandert, bevor es endgültig verschwindet.
PAPIERKORB = "geloescht"


def _bezeichnung(anhang) -> tuple[str, str]:
    """Datum und Benennung für den abgelegten Dateinamen."""
    if anhang.ereignis_id:
        return anhang.ereignis.datum.isoformat(), anhang.ereignis.bezeichnung
    benennung = anhang.beschriftung or str(anhang.bereich)
    return timezone.localdate().isoformat(), benennung


def ablagepfad(anhang, dateiname: str) -> str:
    datum, benennung = _bezeichnung(anhang)
    objekt = slugify(anhang.bereich.objekt.name) or "objekt"
    endung = Path(dateiname).suffix.lower()
    kurz = str(anhang.kennung)[:6]
    return f"{objekt}/{datum}_{slugify(benennung)[:60] or 'anhang'}_{kurz}{endung}"


def vorschaupfad(anhang, dateiname: str) -> str:
    objekt = slugify(anhang.bereich.objekt.name) or "objekt"
    return f"{objekt}/vorschau/{str(anhang.kennung)[:6]}.jpg"


class Anhang(models.Model):
    kennung = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    bereich = models.ForeignKey(
        "wartung.Bereich",
        on_delete=models.CASCADE,
        related_name="anhaenge",
        verbose_name=_("Bereich"),
    )
    ereignis = models.ForeignKey(
        "wartung.Ereignis",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="anhaenge",
        verbose_name=_("Ereignis"),
        help_text=_("Leer lassen bei Unterlagen, die zum Bauteil gehören."),
    )
    datei = models.FileField(_("Datei"), upload_to=ablagepfad, max_length=300)
    vorschau = models.ImageField(
        _("Vorschau"), upload_to=vorschaupfad, max_length=300, null=True, blank=True
    )
    dateiname = models.CharField(_("ursprünglicher Dateiname"), max_length=255)
    inhaltstyp = models.CharField(_("Inhaltstyp"), max_length=100, blank=True)
    groesse = models.PositiveIntegerField(_("Größe in Bytes"), default=0)
    beschriftung = models.CharField(
        _("Beschriftung"),
        max_length=200,
        blank=True,
        help_text=_('Etwa "Typenschild" oder "Rechnung Fa. Berg".'),
    )
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anhaenge",
        verbose_name=_("hochgeladen von"),
    )
    hochgeladen_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Anhang")
        verbose_name_plural = _("Anhänge")
        ordering = ["hochgeladen_am"]

    def __str__(self) -> str:
        return self.beschriftung or self.dateiname

    @property
    def ist_bild(self) -> bool:
        return self.inhaltstyp.startswith("image/")

    def _ableiten(self):
        if self.ereignis_id and not self.bereich_id:
            self.bereich_id = self.ereignis.bereich_id

    def full_clean(self, *args, **kwargs):
        self._ableiten()
        super().full_clean(*args, **kwargs)

    def clean(self):
        if self.ereignis_id and self.bereich_id and self.ereignis.bereich_id != self.bereich_id:
            raise ValidationError({"ereignis": _("Das Ereignis gehört zu einem anderen Bereich.")})

    def save(self, *args, **kwargs):
        self._ableiten()
        super().save(*args, **kwargs)


@receiver(post_delete, sender=Anhang)
def _in_den_papierkorb(sender, instance, **kwargs):
    """Verschiebt die Dateien statt sie zu löschen.

    Hängt am Signal und nicht an einer Methode: Beim Löschen eines Ereignisses
    oder Bereichs räumt Django die Anhänge gebündelt ab, ohne delete() je Zeile
    aufzurufen -- eine Methode würde genau diese Fälle verpassen.
    """
    korb = Path(settings.MEDIA_ROOT) / PAPIERKORB
    for feld in (instance.datei, instance.vorschau):
        if not feld:
            continue
        try:
            quelle = Path(feld.path)
        except (ValueError, NotImplementedError):
            continue
        if not quelle.exists():
            continue
        korb.mkdir(parents=True, exist_ok=True)
        quelle.replace(korb / quelle.name)
