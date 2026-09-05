"""ICS-Kalenderfeed (SPEC 7).

Von Hand erzeugt statt per Bibliothek: Es sind ganztaegige Termine ohne
Wiederholungsregeln, das sind zwanzig Zeilen.

Der Feed zeigt alle aktiven Aufgaben, auch die ruhender Objekte. Die Ruhezeit
unterdrueckt Meldungen -- ein Kalender meldet aber nicht, er plant, und beim
Planen ist der Termin am Sommerhaus gerade nuetzlich.
"""

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext as _

from .faelligkeit import uebersicht


def _maskieren(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _falten(zeile: str) -> str:
    """ICS erlaubt hoechstens 75 Oktette je Zeile; laengere werden umbrochen."""
    roh = zeile.encode("utf-8")
    if len(roh) <= 75:
        return zeile
    teile, rest = [], roh
    teile.append(rest[:73])
    rest = rest[73:]
    while rest:
        teile.append(b" " + rest[:72])
        rest = rest[72:]
    return "\r\n".join(teil.decode("utf-8", errors="ignore") for teil in teile)


def feed(heute: dt.date | None = None) -> str:
    heute = heute or timezone.localdate()
    zeitstempel = timezone.now().strftime("%Y%m%dT%H%M%SZ")

    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Wartungsbuch//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_maskieren(_('Wartungsbuch'))}",
    ]

    for eintrag in uebersicht(heute=heute):
        aufgabe = eintrag.aufgabe
        beginn = eintrag.faellig_am
        titel = f"{aufgabe.taetigkeit.name} – {aufgabe.bereich.objekt.name}"
        beschreibung = f"{aufgabe.bereich} · {eintrag.status_text}"
        if eintrag.letzte_erledigung:
            beschreibung += f" · {_('zuletzt')}: {eintrag.letzte_erledigung.isoformat()}"
        zeilen += [
            "BEGIN:VEVENT",
            f"UID:aufgabe-{aufgabe.pk}-{beginn.isoformat()}@wartungsbuch",
            f"DTSTAMP:{zeitstempel}",
            f"DTSTART;VALUE=DATE:{beginn.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(beginn + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            _falten(f"SUMMARY:{_maskieren(titel)}"),
            _falten(f"DESCRIPTION:{_maskieren(beschreibung)}"),
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    zeilen.append("END:VCALENDAR")
    return "\r\n".join(zeilen) + "\r\n"
