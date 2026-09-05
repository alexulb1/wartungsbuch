"""Tests fuer die Zeitplanung des Versands (SPEC 6, SPEC 10.2).

Anlass ist eine Annahme aus der Spezifikation: "Der NAS laeuft nachts durch."
Darauf sollte sich die Wochenmail nicht verlassen muessen. Deshalb entscheidet
nicht der Zeitplaner, ob verschickt wird, sondern der Befehl selbst -- und zwar
hoechstens einmal je Woche, mit Nachholen, wenn der Versandtag ausgefallen ist.
So genuegt ein stumpfer Zeitplaner, der stuendlich anklopft.
"""

import datetime as dt
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import (
    Aufgabe,
    Benutzer,
    Bereich,
    BereichsTyp,
    Einheit,
    Ereignis,
    Mailversand,
    Objekt,
    ObjektTyp,
    Taetigkeit,
)
from .versandplan import soll_senden, wochenkennung

MONTAG = 0
DIENSTAG = 1
SONNTAG = 6


def zeitpunkt(text):
    return timezone.make_aware(dt.datetime.fromisoformat(text))


class SollSendenTest(TestCase):
    """Reine Entscheidungslogik, ohne Datenbank."""

    def test_am_versandtag_zur_stunde(self):
        self.assertTrue(soll_senden(zeitpunkt("2027-01-11T07:00"), None, MONTAG, 7))

    def test_am_versandtag_zu_frueh(self):
        self.assertFalse(soll_senden(zeitpunkt("2027-01-11T06:59"), None, MONTAG, 7))

    def test_vor_dem_versandtag(self):
        # Montag, 11.01.2027 -- der Versandtag Dienstag kommt erst noch.
        self.assertFalse(soll_senden(zeitpunkt("2027-01-11T09:00"), None, DIENSTAG, 7))

    def test_holt_einen_ausgefallenen_versandtag_nach(self):
        """War der NAS am Montag aus, geht die Mail am Dienstag raus."""
        self.assertTrue(soll_senden(zeitpunkt("2027-01-12T09:00"), None, MONTAG, 7))

    def test_nicht_zweimal_in_derselben_woche(self):
        montag = wochenkennung(zeitpunkt("2027-01-11T07:00"))
        self.assertFalse(soll_senden(zeitpunkt("2027-01-13T09:00"), montag, MONTAG, 7))

    def test_in_der_folgewoche_wieder(self):
        montag = wochenkennung(zeitpunkt("2027-01-11T07:00"))
        self.assertTrue(soll_senden(zeitpunkt("2027-01-18T07:00"), montag, MONTAG, 7))

    def test_stuendliches_anklopfen_erzeugt_keine_zweite_mail(self):
        letzte = None
        gesendet = 0
        for stunde in range(24):
            jetzt = zeitpunkt(f"2027-01-11T{stunde:02d}:00")
            if soll_senden(jetzt, letzte, MONTAG, 7):
                gesendet += 1
                letzte = wochenkennung(jetzt)
        self.assertEqual(gesendet, 1)

    def test_jahreswechsel_wird_ueber_die_iso_woche_behandelt(self):
        """Der 1. Januar kann noch zur letzten Woche des Vorjahres gehören."""
        self.assertEqual(wochenkennung(zeitpunkt("2027-01-01T07:00")), "2026-W53")


class WochenmailPlanungTest(TestCase):
    def setUp(self):
        benutzer = Benutzer.objects.create_user("ich@example.org")
        haus_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        wp_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")
        objekt = Objekt.objects.create(name="Haupthaus", typ=haus_typ)
        bereich = Bereich.objects.create(objekt=objekt, typ=wp_typ)
        aufgabe = Aufgabe.objects.create(
            bereich=bereich, taetigkeit=taetigkeit, intervall_wert=30, intervall_einheit=Einheit.TAGE
        )
        Ereignis.objects.create(bereich=bereich, aufgabe=aufgabe, datum=dt.date(2026, 1, 1))
        # Seit Einführung der Berechtigungen sieht man nur Zugewiesenes (SPEC 2).
        benutzer.zugewiesene_objekte.add(objekt)

    def lauf(self, **optionen):
        call_command("wochenmail", stdout=StringIO(), **optionen)

    def test_geplanter_lauf_verschickt_nur_einmal_je_woche(self):
        self.lauf(jetzt="2027-01-11T07:00", geplant=True)
        self.lauf(jetzt="2027-01-11T08:00", geplant=True)
        self.lauf(jetzt="2027-01-13T08:00", geplant=True)
        self.assertEqual(len(mail.outbox), 1)

    def test_geplanter_lauf_schweigt_vor_dem_versandtag(self):
        self.lauf(jetzt="2027-01-12T07:00", geplant=True, wochentag=3)
        self.assertEqual(len(mail.outbox), 0)

    def test_ohne_planung_wird_immer_verschickt(self):
        """Von Hand aufgerufen, soll der Befehl tun, was man ihm sagt."""
        self.lauf(stichtag="2027-01-11")
        self.lauf(stichtag="2027-01-11")
        self.assertEqual(len(mail.outbox), 2)

    def test_haelt_den_versand_fest(self):
        self.lauf(jetzt="2027-01-11T07:00", geplant=True)
        eintrag = Mailversand.objects.get()
        self.assertEqual(eintrag.anzahl_mails, 1)
        self.assertEqual(eintrag.woche, "2027-W02")
