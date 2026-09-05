"""Tests fuer Wochenmail, Kalender-Feed und CSV-Ausgabe (SPEC 6, SPEC 7)."""

import datetime as dt
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import (
    Aufgabe,
    Benutzer,
    Bereich,
    BereichsTyp,
    Einheit,
    Ereignis,
    Objekt,
    ObjektTyp,
    Taetigkeit,
    Zugangsmarke,
    Zweck,
)


def datum(text):
    return dt.date.fromisoformat(text)


class Bestand(TestCase):
    def setUp(self):
        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")

        haus_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus", name_sv="Hus")
        sommer_typ = ObjektTyp.objects.create(schluessel="sommer", name_de="Sommerhaus", name_sv="Sommarstuga")
        wp_typ = BereichsTyp.objects.create(
            schluessel="waermepumpe", name_de="Wärmepumpe", name_sv="Värmepump"
        )
        self.filter = Taetigkeit.objects.create(
            schluessel="luftfilter", name_de="Luftfilter wechseln", name_sv="Byta luftfilter"
        )
        self.streichen = Taetigkeit.objects.create(schluessel="streichen", name_de="Streichen")

        self.haus = Objekt.objects.create(name="Haupthaus", typ=haus_typ)
        self.sommerhaus = Objekt.objects.create(
            name="Sommerhaus", typ=sommer_typ, aktiv_ab_monat=4, aktiv_bis_monat=10
        )
        self.wp = Bereich.objects.create(objekt=self.haus, typ=wp_typ)
        self.klima = Bereich.objects.create(objekt=self.sommerhaus, typ=wp_typ)

        self.ueberfaellig = Aufgabe.objects.create(
            bereich=self.wp, taetigkeit=self.filter, intervall_wert=30, intervall_einheit=Einheit.TAGE
        )
        Ereignis.objects.create(bereich=self.wp, aufgabe=self.ueberfaellig, datum=datum("2026-01-01"))

        self.im_sommerhaus = Aufgabe.objects.create(
            bereich=self.klima, taetigkeit=self.filter, intervall_wert=30, intervall_einheit=Einheit.TAGE
        )
        Ereignis.objects.create(bereich=self.klima, aufgabe=self.im_sommerhaus, datum=datum("2026-10-01"))

    def wochenmail(self, stichtag="2027-01-15"):
        call_command("wochenmail", stichtag=stichtag, stdout=StringIO())


class WochenmailTest(Bestand):
    def test_geht_an_aktive_konten(self):
        self.wochenmail()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ich@example.org"])

    def test_stillgelegte_konten_bekommen_nichts(self):
        self.benutzer.is_active = False
        self.benutzer.save()
        self.wochenmail()
        self.assertEqual(len(mail.outbox), 0)

    def test_keine_mail_wenn_nichts_ansteht(self):
        """Stille ist besser als eine Mail ohne Inhalt."""
        Aufgabe.objects.all().delete()
        self.wochenmail()
        self.assertEqual(len(mail.outbox), 0)

    def test_nennt_ueberfaellige_aufgaben(self):
        self.wochenmail()
        self.assertIn("Luftfilter wechseln", mail.outbox[0].body)
        self.assertIn("Haupthaus", mail.outbox[0].body)

    def test_ruhendes_objekt_taucht_im_winter_nicht_auf(self):
        self.wochenmail(stichtag="2027-01-15")
        self.assertNotIn("Sommerhaus", mail.outbox[0].body)

    def test_zum_saisonstart_kommt_die_ankunftsliste(self):
        self.wochenmail(stichtag="2027-04-05")
        text = mail.outbox[0].body
        self.assertIn("Sommerhaus", text)
        self.assertIn("Saison", text)

    def test_weit_entfernte_aufgaben_stehen_nicht_drin(self):
        """14 Tage Vorschau, nicht der ganze Kalender (SPEC 6)."""
        spaeter = Aufgabe.objects.create(
            bereich=self.wp, taetigkeit=self.streichen, intervall_wert=10, intervall_einheit=Einheit.JAHRE
        )
        Ereignis.objects.create(bereich=self.wp, aufgabe=spaeter, datum=datum("2026-06-01"))
        self.wochenmail()
        self.assertNotIn("Streichen", mail.outbox[0].body)

    def test_jede_aufgabe_bekommt_einen_eigenen_abhaklink(self):
        self.wochenmail()
        links = [w for w in mail.outbox[0].body.split() if "/erledigt/" in w]
        self.assertEqual(len(links), 1)
        self.assertEqual(Zugangsmarke.objects.filter(zweck=Zweck.ERLEDIGUNG).count(), 1)

    def test_der_link_hakt_genau_diese_aufgabe_ab(self):
        self.wochenmail()
        roh = [w for w in mail.outbox[0].body.split() if "/erledigt/" in w][0]
        roh = roh.rstrip(".").split("/erledigt/")[1].strip("/")
        antwort = self.client.post(
            reverse("wartung:erledigt_mit_marke", args=[roh]), {"datum": "2027-01-15"}
        )
        self.assertEqual(antwort.status_code, 200)
        neu = Ereignis.objects.filter(datum=datum("2027-01-15")).get()
        self.assertEqual(neu.aufgabe, self.ueberfaellig)

    def test_in_der_sprache_des_empfaengers(self):
        self.benutzer.sprache = "sv"
        self.benutzer.save()
        self.wochenmail()
        self.assertIn("Byta luftfilter", mail.outbox[0].body)
        self.assertNotIn("Luftfilter wechseln", mail.outbox[0].body)

    def test_jeder_empfaenger_bekommt_eigene_marken(self):
        Benutzer.objects.create_user("du@example.org")
        self.wochenmail()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(Zugangsmarke.objects.filter(zweck=Zweck.ERLEDIGUNG).count(), 2)


class KalenderTest(Bestand):
    def test_feed_ist_ohne_anmeldung_erreichbar(self):
        antwort = self.client.get(
            reverse("wartung:kalender", args=[self.benutzer.kalender_schluessel])
        )
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort["Content-Type"], "text/calendar; charset=utf-8")

    def test_enthaelt_faellige_aufgaben_als_termine(self):
        antwort = self.client.get(
            reverse("wartung:kalender", args=[self.benutzer.kalender_schluessel])
        )
        text = antwort.content.decode()
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("BEGIN:VEVENT", text)
        self.assertIn("Luftfilter wechseln", text)

    def test_falscher_schluessel_ergibt_nichts(self):
        antwort = self.client.get(reverse("wartung:kalender", args=["erfunden"]))
        self.assertEqual(antwort.status_code, 404)

    def test_schluessel_wird_beim_anlegen_vergeben(self):
        neuer = Benutzer.objects.create_user("neu@example.org")
        self.assertTrue(neuer.kalender_schluessel)
        self.assertNotEqual(neuer.kalender_schluessel, self.benutzer.kalender_schluessel)


class CsvTest(Bestand):
    def test_verlangt_anmeldung(self):
        self.assertEqual(self.client.get(reverse("wartung:export_csv")).status_code, 302)

    def test_enthaelt_alle_ereignisse(self):
        self.client.force_login(self.benutzer)
        antwort = self.client.get(reverse("wartung:export_csv"))
        self.assertEqual(antwort.status_code, 200)
        zeilen = antwort.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(zeilen), 1 + Ereignis.objects.count())
        self.assertIn("Haupthaus", antwort.content.decode("utf-8-sig"))

    def test_traegt_einen_dateinamen(self):
        self.client.force_login(self.benutzer)
        antwort = self.client.get(reverse("wartung:export_csv"))
        self.assertIn("attachment", antwort["Content-Disposition"])
        self.assertIn(".csv", antwort["Content-Disposition"])


class ProfilVerweiseTest(Bestand):
    def test_profil_zeigt_die_kalenderadresse(self):
        self.client.force_login(self.benutzer)
        antwort = self.client.get(reverse("wartung:profil"))
        self.assertContains(antwort, self.benutzer.kalender_schluessel)

    def test_profil_bietet_die_csv_ausgabe_an(self):
        self.client.force_login(self.benutzer)
        antwort = self.client.get(reverse("wartung:profil"))
        self.assertContains(antwort, reverse("wartung:export_csv"))

    def test_kopfzeile_bietet_abmelden(self):
        self.client.force_login(self.benutzer)
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, reverse("wartung:abmelden"))


class MarkenAufraeumenTest(Bestand):
    def test_alte_marken_verschwinden(self):
        """Verbrauchte und abgelaufene Marken sind Ballast -- und je weniger
        davon liegt, desto weniger gibt es zu verlieren."""
        import datetime as dt

        from django.utils import timezone

        alt, _roh = Zugangsmarke.objects.anlegen(Zweck.ANMELDUNG, self.benutzer)
        Zugangsmarke.objects.filter(pk=alt.pk).update(
            gueltig_bis=timezone.now() - dt.timedelta(days=40),
            erstellt_am=timezone.now() - dt.timedelta(days=40),
        )
        frisch, _roh2 = Zugangsmarke.objects.anlegen(Zweck.ANMELDUNG, self.benutzer)

        call_command("marken_aufraeumen", stdout=StringIO())

        self.assertFalse(Zugangsmarke.objects.filter(pk=alt.pk).exists())
        self.assertTrue(Zugangsmarke.objects.filter(pk=frisch.pk).exists())

    def test_gueltige_marken_bleiben(self):
        marke, _roh = Zugangsmarke.objects.anlegen(
            Zweck.ERLEDIGUNG, self.benutzer, aufgabe=self.ueberfaellig
        )
        call_command("marken_aufraeumen", stdout=StringIO())
        self.assertTrue(Zugangsmarke.objects.filter(pk=marke.pk).exists())
