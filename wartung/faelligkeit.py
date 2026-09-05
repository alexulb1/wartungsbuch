"""Faelligkeitsberechnung (SPEC 5, SPEC 6).

Die Faelligkeit wird nirgends gespeichert. Sie ergibt sich aus dem juengsten
Ereignis plus Intervall und wird bei jeder Abfrage neu bestimmt -- deshalb kann
sie nicht veralten, und ein nachgetragenes Ereignis korrigiert sie rueckwirkend.

"heute" wird ueberall hineingereicht statt aus der Systemzeit gelesen: Das haelt
die Berechnung pruefbar und erlaubt Vorschauen auf andere Stichtage.
"""

import datetime as dt
from calendar import monthrange
from dataclasses import dataclass

from django.db import models
from django.db.models import OuterRef, Subquery
from django.utils.translation import gettext_lazy as _

from .models import Aufgabe, Einheit, Ereignis, Modus

#: Wie weit die Wochenmail vorausschaut (SPEC 6).
VORSCHAU_TAGE = 14


class Status(models.TextChoices):
    NIE_ERLEDIGT = "nie_erledigt", _("noch nie erledigt")
    UEBERFAELLIG = "ueberfaellig", _("überfällig")
    FAELLIG = "faellig", _("heute fällig")
    BALD = "bald", _("bald fällig")
    OFFEN = "offen", _("offen")


@dataclass(frozen=True)
class Faelligkeit:
    """Das Urteil ueber eine Aufgabe zu einem Stichtag."""

    aufgabe: Aufgabe
    letzte_erledigung: dt.date | None
    faellig_am: dt.date
    status: str
    tage_ueberfaellig: int
    wird_gemeldet: bool

    @property
    def status_text(self) -> str:
        """Der Status im Klartext, in der aktiven Sprache."""
        return Status(self.status).label


def monate_addieren(datum: dt.date, monate: int) -> dt.date:
    """Addiert Monate und kappt auf das Monatsende.

    Der 31. Januar plus einen Monat ist der 28. Februar -- es gibt keinen 31.
    Februar, und ein Ueberlauf in den Maerz waere ueberraschend.
    """
    gesamt = datum.month - 1 + monate
    jahr = datum.year + gesamt // 12
    monat = gesamt % 12 + 1
    return dt.date(jahr, monat, min(datum.day, monthrange(jahr, monat)[1]))


def intervall_addieren(datum: dt.date, wert: int, einheit: str) -> dt.date:
    if einheit == Einheit.TAGE:
        return datum + dt.timedelta(days=wert)
    if einheit == Einheit.MONATE:
        return monate_addieren(datum, wert)
    if einheit == Einheit.JAHRE:
        return monate_addieren(datum, wert * 12)
    raise ValueError(f"Unbekannte Einheit: {einheit}")


def _kalendertermin(aufgabe: Aufgabe, jahr: int) -> dt.date:
    monat = aufgabe.kalender_monat
    tag = aufgabe.kalender_tag or 1
    return dt.date(jahr, monat, min(tag, monthrange(jahr, monat)[1]))


def _kalender_faelligkeit(
    aufgabe: Aufgabe, letzte_erledigung: dt.date | None, heute: dt.date
) -> dt.date:
    if letzte_erledigung is None:
        # Noch nie erledigt: der letzte vergangene Termin steht offen.
        jahr = heute.year if _kalendertermin(aufgabe, heute.year) <= heute else heute.year - 1
        return _kalendertermin(aufgabe, jahr)

    # Der naechste Termin nach der Erledigung -- und von dort die restlichen
    # Perioden. So kann eine verspaetete Erledigung den Termin nicht
    # verschieben, und eine fruehe ueberspringt ihn nicht.
    jahr = letzte_erledigung.year
    if _kalendertermin(aufgabe, jahr) <= letzte_erledigung:
        jahr += 1
    return _kalendertermin(aufgabe, jahr + aufgabe.intervall_wert - 1)


def naechste_faelligkeit(
    aufgabe: Aufgabe, letzte_erledigung: dt.date | None, heute: dt.date
) -> dt.date:
    if aufgabe.modus == Modus.KALENDER:
        return _kalender_faelligkeit(aufgabe, letzte_erledigung, heute)
    if letzte_erledigung is None:
        # Ohne Anhaltspunkt gibt es nichts zu rechnen: dann eben jetzt.
        return heute
    return intervall_addieren(letzte_erledigung, aufgabe.intervall_wert, aufgabe.intervall_einheit)


def bewerten(
    aufgabe: Aufgabe,
    letzte_erledigung: dt.date | None,
    heute: dt.date,
    vorschau_tage: int = VORSCHAU_TAGE,
) -> Faelligkeit:
    faellig_am = naechste_faelligkeit(aufgabe, letzte_erledigung, heute)
    tage_ueberfaellig = 0

    if letzte_erledigung is None:
        # Eigener Status: "ueberfaellig seit 1970" waere eine Luege.
        status = Status.NIE_ERLEDIGT
    elif faellig_am < heute:
        status = Status.UEBERFAELLIG
        tage_ueberfaellig = (heute - faellig_am).days
    elif faellig_am == heute:
        status = Status.FAELLIG
    elif faellig_am <= heute + dt.timedelta(days=vorschau_tage):
        status = Status.BALD
    else:
        status = Status.OFFEN

    return Faelligkeit(
        aufgabe=aufgabe,
        letzte_erledigung=letzte_erledigung,
        faellig_am=faellig_am,
        status=status,
        tage_ueberfaellig=tage_ueberfaellig,
        # Die Ruhezeit unterdrueckt nur die Meldung, nicht die Berechnung.
        wird_gemeldet=aufgabe.bereich.objekt.meldet_im_monat(heute.month),
    )


def uebersicht(
    heute: dt.date,
    vorschau_tage: int = VORSCHAU_TAGE,
    nur_meldbare: bool = False,
    fuer=None,
) -> list[Faelligkeit]:
    """Alle aktiven Aufgaben mit ihrem Urteil, das Draengendste zuerst.

    Holt die letzte Erledigung je Aufgabe in derselben Abfrage -- sonst waere
    das eine Abfrage pro Aufgabe.

    "fuer" schraenkt auf die Objekte ein, die diese Person sehen darf. Ohne
    Angabe bleibt es bei allem -- das ist der Weg fuer Verwaltungsaufgaben, die
    ohne Benutzer laufen.
    """
    letzte_erledigung = (
        Ereignis.objects.filter(aufgabe=OuterRef("pk")).order_by("-datum").values("datum")[:1]
    )
    aufgaben = (
        Aufgabe.objects.filter(aktiv=True)
        .select_related("bereich__objekt__typ", "bereich__typ", "taetigkeit")
        .annotate(letzte_erledigung=Subquery(letzte_erledigung))
    )
    if fuer is not None:
        # Der Import steht in der Funktion: sichtbarkeit importiert models,
        # auf Modulebene gaebe das einen Ringschluss.
        from .sichtbarkeit import sichtbare_objekte

        aufgaben = aufgaben.filter(bereich__objekt__in=sichtbare_objekte(fuer))

    eintraege = [
        bewerten(aufgabe, aufgabe.letzte_erledigung, heute, vorschau_tage) for aufgabe in aufgaben
    ]
    if nur_meldbare:
        eintraege = [eintrag for eintrag in eintraege if eintrag.wird_gemeldet]
    return sorted(eintraege, key=lambda eintrag: (eintrag.faellig_am, eintrag.aufgabe.pk))
