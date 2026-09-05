"""Protokoll der verschickten Wochenmails (SPEC 6).

Eine Zeile je Kalenderwoche. Sie ist zugleich die Sperre, die einen zweiten
Versand in derselben Woche verhindert -- die Eindeutigkeit erledigt das in der
Datenbank, nicht im Programm.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Mailversand(models.Model):
    woche = models.CharField(_("Woche"), max_length=9, unique=True)
    gesendet_am = models.DateTimeField(_("gesendet am"), auto_now_add=True)
    anzahl_mails = models.PositiveIntegerField(_("Anzahl Mails"), default=0)
    anzahl_eintraege = models.PositiveIntegerField(_("Anzahl Einträge"), default=0)

    class Meta:
        verbose_name = _("Mailversand")
        verbose_name_plural = _("Mailversand")
        ordering = ["-gesendet_am"]

    def __str__(self) -> str:
        return f"{self.woche}: {self.anzahl_mails} Mail(s)"
