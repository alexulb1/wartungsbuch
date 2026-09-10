"""Sitzungen laufen bei Untätigkeit ab.

Django hält eine Sitzung standardmäßig zwei Wochen, unabhängig davon, ob sie
benutzt wird. Hier gilt stattdessen ein gleitendes Fenster: Jede Anfrage stellt
die Uhr zurück, wer eine Weile nichts tut, muss sich neu anmelden.
"""

import datetime as dt

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Benutzer


class EinstellungenTest(TestCase):
    def test_die_sitzungsdauer_ist_kuerzer_als_djangos_vorgabe(self):
        """Zwei Wochen sind die Django-Vorgabe und zu lang für ein Konto, das
        auf einem Handy offen bleibt."""
        self.assertLess(settings.SESSION_COOKIE_AGE, 14 * 24 * 3600)

    def test_die_uhr_wird_bei_jeder_anfrage_zurueckgestellt(self):
        """Ohne das wäre es kein Ablauf bei Untätigkeit, sondern ein starrer
        Ablauf ab Anmeldung."""
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_die_dauer_kommt_aus_der_umgebung(self):
        from wartungsbuch.settings import sitzungsdauer

        self.assertEqual(sitzungsdauer({"SITZUNGSDAUER_STUNDEN": "8"}), 8 * 3600)
        self.assertEqual(sitzungsdauer({}), 48 * 3600)


class AblaufTest(TestCase):
    def setUp(self):
        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.client.force_login(self.benutzer)

    def test_frisch_angemeldet_kommt_man_durch(self):
        self.assertEqual(self.client.get(reverse("wartung:dashboard")).status_code, 200)

    @override_settings(SESSION_COOKIE_AGE=3600)
    def test_nach_untaetigkeit_ist_die_sitzung_abgelaufen(self):
        from django.contrib.sessions.models import Session

        sitzung = Session.objects.get()
        sitzung.expire_date = timezone.now() - dt.timedelta(minutes=1)
        sitzung.save()

        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertEqual(antwort.status_code, 302)
        self.assertIn("/anmelden/", antwort["Location"])

    def test_benutzung_verlaengert_die_sitzung(self):
        from django.contrib.sessions.models import Session

        vorher = Session.objects.get().expire_date
        # Ein Aufruf muss das Ablaufdatum nach hinten schieben.
        self.client.get(reverse("wartung:dashboard"))
        nachher = Session.objects.get().expire_date
        self.assertGreater(nachher, vorher)


class AufraeumenTest(TestCase):
    """Django legt Sitzungen in der Datenbank ab und räumt nicht von selbst
    auf -- ohne diesen Schritt wächst die Tabelle für immer."""

    def test_abgelaufene_sitzungen_werden_entfernt(self):
        from io import StringIO

        from django.contrib.sessions.models import Session
        from django.core.management import call_command

        benutzer = Benutzer.objects.create_user("du@example.org")
        self.client.force_login(benutzer)
        sitzung = Session.objects.get()
        sitzung.expire_date = timezone.now() - dt.timedelta(days=1)
        sitzung.save()

        call_command("clearsessions", stdout=StringIO())

        self.assertFalse(Session.objects.filter(pk=sitzung.pk).exists())

    def test_der_planer_raeumt_sitzungen_mit_auf(self):
        from io import StringIO

        from django.core.management import call_command

        ausgabe = StringIO()
        call_command("planer", einmal=True, jetzt="2027-01-11T05:00", stdout=ausgabe, stderr=ausgabe)
        self.assertNotIn("fehlgeschlagen", ausgabe.getvalue())
        from wartung.management.commands.planer import Command

        self.assertTrue(hasattr(Command, "sitzungen_aufraeumen"))
