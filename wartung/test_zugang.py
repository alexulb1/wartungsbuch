"""Tests fuer Anmeldung und Ein-Klick-Abhaken (SPEC 2, SPEC 6, SPEC 8).

Der wichtigste Test dieser Datei ist test_abhakmarke_taugt_nicht_zur_anmeldung:
Die Trennung der beiden Markenarten ist die Zusicherung, dass ein abgefangener
Link aus der Wochenmail genau eine Aufgabe abhaken kann und sonst nichts.
"""

import datetime as dt

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


def bestand():
    objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
    bereichs_typ = BereichsTyp.objects.create(schluessel="waermepumpe", name_de="Wärmepumpe")
    taetigkeit = Taetigkeit.objects.create(schluessel="luftfilter", name_de="Luftfilter wechseln")
    objekt = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
    bereich = Bereich.objects.create(objekt=objekt, typ=bereichs_typ)
    return Aufgabe.objects.create(
        bereich=bereich, taetigkeit=taetigkeit, intervall_wert=30, intervall_einheit=Einheit.TAGE
    )


class ZugangsmarkeTest(TestCase):
    def setUp(self):
        self.benutzer = Benutzer.objects.create_user("ich@example.org")
        self.aufgabe = bestand()
        # Seit Einführung der Berechtigungen sieht man nur Zugewiesenes (SPEC 2).
        self.benutzer.zugewiesene_objekte.add(self.aufgabe.bereich.objekt)

    def test_marke_ist_nur_einmal_einloesbar(self):
        marke, roh = Zugangsmarke.objects.anlegen(Zweck.ANMELDUNG, self.benutzer)
        self.assertIsNotNone(Zugangsmarke.objects.einloesen(roh, Zweck.ANMELDUNG))
        self.assertIsNone(Zugangsmarke.objects.einloesen(roh, Zweck.ANMELDUNG))

    def test_abgelaufene_marke_wird_abgelehnt(self):
        marke, roh = Zugangsmarke.objects.anlegen(Zweck.ANMELDUNG, self.benutzer)
        marke.gueltig_bis = timezone.now() - dt.timedelta(minutes=1)
        marke.save()
        self.assertIsNone(Zugangsmarke.objects.einloesen(roh, Zweck.ANMELDUNG))

    def test_abhakmarke_taugt_nicht_zur_anmeldung(self):
        """Wer einen Abhak-Link abfaengt, kommt damit nicht in die Anwendung."""
        _, roh = Zugangsmarke.objects.anlegen(
            Zweck.ERLEDIGUNG, self.benutzer, aufgabe=self.aufgabe
        )
        self.assertIsNone(Zugangsmarke.objects.einloesen(roh, Zweck.ANMELDUNG))
        self.assertIsNotNone(Zugangsmarke.objects.einloesen(roh, Zweck.ERLEDIGUNG))

    def test_die_marke_selbst_wird_nicht_gespeichert(self):
        """Ein Blick in die Datenbank ergibt keine benutzbaren Links."""
        _, roh = Zugangsmarke.objects.anlegen(Zweck.ANMELDUNG, self.benutzer)
        gespeichert = Zugangsmarke.objects.get()
        self.assertNotIn(roh, str(gespeichert.__dict__))

    def test_unsinn_wird_abgelehnt(self):
        self.assertIsNone(Zugangsmarke.objects.einloesen("erfunden", Zweck.ANMELDUNG))
        self.assertIsNone(Zugangsmarke.objects.einloesen("", Zweck.ANMELDUNG))


class AnmeldungTest(TestCase):
    def setUp(self):
        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")

    def test_bekannte_adresse_bekommt_eine_mail(self):
        antwort = self.client.post(reverse("wartung:anmelden"), {"email": "ich@example.org"})
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ich@example.org", mail.outbox[0].to)

    def test_unbekannte_adresse_erfaehrt_nichts(self):
        """Keine Auskunft darueber, wer ein Konto hat."""
        bekannt = self.client.post(reverse("wartung:anmelden"), {"email": "ich@example.org"})
        unbekannt = self.client.post(reverse("wartung:anmelden"), {"email": "fremd@example.org"})
        self.assertEqual(bekannt.content, unbekannt.content)
        self.assertEqual(len(mail.outbox), 1)

    def test_link_aus_der_mail_meldet_an(self):
        self.client.post(reverse("wartung:anmelden"), {"email": "ich@example.org"})
        marke, roh = Zugangsmarke.objects.first(), None
        # Den Rohwert aus der Mail holen -- so, wie es der Empfaenger tut.
        for wort in mail.outbox[0].body.split():
            if "/anmelden/" in wort:
                roh = wort.rstrip(".").split("/anmelden/")[1].strip("/")
        antwort = self.client.get(reverse("wartung:anmelden_mit_marke", args=[roh]))
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(self.client.get(reverse("wartung:dashboard")).status_code, 200)

    def test_zweiter_aufruf_desselben_links_meldet_nicht_an(self):
        _, roh = Zugangsmarke.objects.anlegen(Zweck.ANMELDUNG, self.benutzer)
        self.client.get(reverse("wartung:anmelden_mit_marke", args=[roh]))
        self.client.logout()
        self.client.get(reverse("wartung:anmelden_mit_marke", args=[roh]))
        self.assertEqual(self.client.get(reverse("wartung:dashboard")).status_code, 302)

    def test_zu_viele_anfragen_werden_gebremst(self):
        for _ in range(3):
            self.client.post(reverse("wartung:anmelden"), {"email": "ich@example.org"})
        self.client.post(reverse("wartung:anmelden"), {"email": "ich@example.org"})
        self.assertEqual(len(mail.outbox), 3)

    def test_abmelden(self):
        self.client.force_login(self.benutzer)
        self.client.post(reverse("wartung:abmelden"))
        self.assertEqual(self.client.get(reverse("wartung:dashboard")).status_code, 302)


class AbhakenPerMarkeTest(TestCase):
    def setUp(self):
        self.benutzer = Benutzer.objects.create_user("ich@example.org")
        self.aufgabe = bestand()
        # Seit Einführung der Berechtigungen sieht man nur Zugewiesenes (SPEC 2).
        self.benutzer.zugewiesene_objekte.add(self.aufgabe.bereich.objekt)
        _, self.roh = Zugangsmarke.objects.anlegen(
            Zweck.ERLEDIGUNG, self.benutzer, aufgabe=self.aufgabe
        )

    def test_formular_ohne_anmeldung_erreichbar(self):
        antwort = self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Luftfilter wechseln")

    def test_blosser_aufruf_veraendert_nichts(self):
        """Mailprogramme und Virenscanner rufen Links vorab ab (SPEC 6)."""
        self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertFalse(Ereignis.objects.exists())

    def test_absenden_legt_ereignis_an(self):
        antwort = self.client.post(
            reverse("wartung:erledigt_mit_marke", args=[self.roh]),
            {"datum": "2026-03-12", "notiz": "RAL 7016"},
        )
        self.assertEqual(antwort.status_code, 200)
        ereignis = Ereignis.objects.get()
        self.assertEqual(ereignis.aufgabe, self.aufgabe)
        self.assertEqual(ereignis.datum, dt.date(2026, 3, 12))
        self.assertEqual(ereignis.erfasst_von, self.benutzer)

    def test_marke_ist_danach_verbraucht(self):
        self.client.post(
            reverse("wartung:erledigt_mit_marke", args=[self.roh]), {"datum": "2026-03-12"}
        )
        antwort = self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertEqual(antwort.status_code, 404)

    def test_marke_verschafft_keinen_zugang_zur_anwendung(self):
        self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertEqual(self.client.get(reverse("wartung:dashboard")).status_code, 302)


class VorbelegungAusMarkeTest(TestCase):
    """Auch ohne Anmeldung ist bekannt, wer abhakt -- die Marke gehört einer
    bestimmten Person."""

    def setUp(self):
        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex Ulb")
        self.aufgabe = bestand()
        # Seit Einführung der Berechtigungen sieht man nur Zugewiesenes (SPEC 2).
        self.benutzer.zugewiesene_objekte.add(self.aufgabe.bereich.objekt)
        _, self.roh = Zugangsmarke.objects.anlegen(
            Zweck.ERLEDIGUNG, self.benutzer, aufgabe=self.aufgabe
        )

    def test_abhakseite_aus_der_mail_traegt_den_namen_des_empfaengers(self):
        antwort = self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertContains(antwort, 'value="Alex Ulb"')
