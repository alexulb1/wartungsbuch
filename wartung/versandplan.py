"""Wann die Wochenmail rausgeht (SPEC 6).

Die Entscheidung liegt hier, nicht beim Zeitplaner. Das hat einen Grund: Ein
Zeitplaner, der genau um 7:00 am Montag ausloest, verliert die Mail, wenn der
Rechner in dieser Minute gerade schlaeft oder neu startet. Klopft stattdessen
etwas stumpf jede Stunde an und entscheidet der Befehl selbst, geht nichts
verloren -- und doppelt verschickt wird trotzdem nichts.
"""

import datetime as dt


def wochenkennung(zeitpunkt: dt.datetime) -> str:
    """ISO-Woche als "2027-W02". Der Jahreswechsel ist damit richtig behandelt:
    Der 1. Januar kann noch zur letzten Woche des Vorjahres gehoeren."""
    jahr, woche, _tag = zeitpunkt.isocalendar()
    return f"{jahr}-W{woche:02d}"


def soll_senden(
    jetzt: dt.datetime,
    letzte_woche: str | None,
    wochentag: int,
    stunde: int,
) -> bool:
    """wochentag: 0 = Montag ... 6 = Sonntag.

    letzte_woche ist die Kennung der zuletzt verschickten Woche. Bewusst die
    Woche und nicht der Zeitstempel: Danach richtet sich die Sperre, und
    danach faellt auch die Entscheidung.
    """
    if letzte_woche is not None and letzte_woche == wochenkennung(jetzt):
        return False
    if jetzt.weekday() < wochentag:
        return False  # Der Versandtag dieser Woche kommt erst noch.
    if jetzt.weekday() == wochentag and jetzt.hour < stunde:
        return False
    # Spaeter in der Woche: der Versandtag ist ausgefallen, wird nachgeholt.
    return True
