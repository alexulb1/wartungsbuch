"""Tests fuer die Zusicherungen des Datenmodells (Schritt 1)."""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import translation

from .models import (
    Aufgabe,
    Benutzer,
    Bereich,
    BereichsTyp,
    Einheit,
    Ereignis,
    Modus,
    Objekt,
    ObjektTyp,
    Sprache,
    Taetigkeit,
)


class UebersetzungTest(TestCase):
    def test_zeigt_bezeichnung_der_aktiven_sprache(self):
        typ = BereichsTyp.objects.create(
            schluessel="waermepumpe",
            name_de="Wärmepumpe",
            name_en="Heat pump",
            name_sv="Värmepump",
        )
        for code, erwartet in [("de", "Wärmepumpe"), ("en", "Heat pump"), ("sv", "Värmepump")]:
            with translation.override(code):
                self.assertEqual(typ.name, erwartet)

    def test_faellt_auf_deutsch_zurueck_wenn_uebersetzung_fehlt(self):
        typ = BereichsTyp.objects.create(schluessel="ortgang", name_de="Ortgangbrett")
        with translation.override("sv"):
            self.assertEqual(typ.name, "Ortgangbrett")


class RuhezeitTest(TestCase):
    """Die Ruhezeit unterdrueckt nur Meldungen (SPEC 6)."""

    def setUp(self):
        self.typ = ObjektTyp.objects.create(schluessel="sommerhaus", name_de="Sommerhaus")

    def test_ohne_ruhezeit_meldet_ganzjaehrig(self):
        objekt = Objekt.objects.create(name="Haupthaus", typ=self.typ)
        self.assertTrue(all(objekt.meldet_im_monat(m) for m in range(1, 13)))

    def test_sommersaison_meldet_nur_innerhalb(self):
        objekt = Objekt.objects.create(
            name="Sommerhaus", typ=self.typ, aktiv_ab_monat=4, aktiv_bis_monat=10
        )
        self.assertTrue(objekt.meldet_im_monat(4))
        self.assertTrue(objekt.meldet_im_monat(10))
        self.assertFalse(objekt.meldet_im_monat(1))
        self.assertFalse(objekt.meldet_im_monat(11))

    def test_zeitraum_ueber_den_jahreswechsel(self):
        objekt = Objekt.objects.create(
            name="Winterhaus", typ=self.typ, aktiv_ab_monat=11, aktiv_bis_monat=3
        )
        self.assertTrue(objekt.meldet_im_monat(12))
        self.assertTrue(objekt.meldet_im_monat(2))
        self.assertFalse(objekt.meldet_im_monat(6))

    def test_halbe_ruhezeit_wird_abgelehnt(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Objekt.objects.create(name="Halb", typ=self.typ, aktiv_ab_monat=4)


class EreignisTest(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="waermepumpe", name_de="Wärmepumpe")
        self.taetigkeit = Taetigkeit.objects.create(
            schluessel="luftfilter-wechseln", name_de="Luftfilter wechseln"
        )
        self.objekt = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.bereich = Bereich.objects.create(objekt=self.objekt, typ=bereichs_typ)
        self.anderer_bereich = Bereich.objects.create(
            objekt=self.objekt, typ=bereichs_typ, bezeichnung_de="Nebengebäude"
        )
        self.aufgabe = Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=self.taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )

    def test_aufgabe_leitet_bereich_und_taetigkeit_ab(self):
        ereignis = Ereignis(aufgabe=self.aufgabe, datum=dt.date(2026, 3, 12))
        ereignis.save()
        self.assertEqual(ereignis.bereich, self.bereich)
        self.assertEqual(ereignis.taetigkeit, self.taetigkeit)

    def test_einmaliges_ereignis_ohne_aufgabe(self):
        ereignis = Ereignis.objects.create(
            bereich=self.bereich, beschreibung="Bad renoviert", datum=dt.date(2019, 6, 1)
        )
        self.assertIsNone(ereignis.aufgabe)
        self.assertEqual(ereignis.bezeichnung, "Bad renoviert")

    def test_ereignis_ohne_taetigkeit_und_ohne_beschreibung_wird_abgelehnt(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ereignis.objects.create(bereich=self.bereich, datum=dt.date(2026, 1, 1))

    def test_aufgabe_aus_fremdem_bereich_wird_beanstandet(self):
        ereignis = Ereignis(
            bereich=self.anderer_bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 1, 1)
        )
        with self.assertRaises(ValidationError):
            ereignis.full_clean()

    def test_datum_darf_in_der_vergangenheit_liegen(self):
        """Dokumentation hinkt der Arbeit nach -- das darf nichts verschieben (SPEC 4)."""
        ereignis = Ereignis(aufgabe=self.aufgabe, datum=dt.date(2020, 1, 1))
        ereignis.full_clean()
        ereignis.save()
        self.assertEqual(ereignis.datum, dt.date(2020, 1, 1))


class AufgabeTest(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        self.bereichs_typ = BereichsTyp.objects.create(schluessel="fassade", name_de="Fassade")
        self.taetigkeit = Taetigkeit.objects.create(schluessel="streichen", name_de="Streichen")
        self.objekt = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.bereich = Bereich.objects.create(
            objekt=self.objekt, typ=self.bereichs_typ, bezeichnung_de="Nord"
        )

    def test_kalendermodus_ohne_monat_wird_beanstandet(self):
        aufgabe = Aufgabe(
            bereich=self.bereich,
            taetigkeit=self.taetigkeit,
            intervall_wert=10,
            intervall_einheit=Einheit.JAHRE,
            modus=Modus.KALENDER,
        )
        with self.assertRaises(ValidationError):
            aufgabe.full_clean()

    def test_gleiche_taetigkeit_zweimal_am_bereich_wird_abgelehnt(self):
        Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=self.taetigkeit,
            intervall_wert=10,
            intervall_einheit=Einheit.JAHRE,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Aufgabe.objects.create(
                bereich=self.bereich,
                taetigkeit=self.taetigkeit,
                intervall_wert=5,
                intervall_einheit=Einheit.JAHRE,
            )

    def test_seiten_werden_ueber_die_bezeichnung_unterschieden(self):
        sued = Bereich.objects.create(
            objekt=self.objekt, typ=self.bereichs_typ, bezeichnung_de="Süd"
        )
        self.assertNotEqual(str(self.bereich), str(sued))
        self.assertEqual(str(sued), "Fassade Süd")


class BenutzerTest(TestCase):
    def test_konto_hat_kein_verwendbares_passwort(self):
        benutzer = Benutzer.objects.create_user("a@example.org", name="Alex", sprache=Sprache.SCHWEDISCH)
        self.assertFalse(benutzer.has_usable_password())
        self.assertEqual(benutzer.sprache, "sv")

    def test_email_ist_eindeutig(self):
        Benutzer.objects.create_user("a@example.org")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Benutzer.objects.create_user("a@example.org")


class AdminTest(TestCase):
    """Der Django-Admin ist die Pflegeoberflaeche (SPEC 9) -- und ohne Passwort
    erreichbar, sobald eine Sitzung besteht (SPEC 2)."""

    def setUp(self):
        self.benutzer = Benutzer.objects.create_user(
            "verwaltung@example.org", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.benutzer)

    def test_uebersichtsseiten_sind_erreichbar(self):
        for pfad in [
            "/admin/",
            "/admin/wartung/objekt/",
            "/admin/wartung/bereich/",
            "/admin/wartung/aufgabe/",
            "/admin/wartung/ereignis/",
            "/admin/wartung/taetigkeit/",
            "/admin/wartung/benutzer/",
        ]:
            with self.subTest(pfad=pfad):
                self.assertEqual(self.client.get(pfad).status_code, 200)

    def test_formulare_sind_erreichbar(self):
        for pfad in ["/admin/wartung/objekt/add/", "/admin/wartung/ereignis/add/"]:
            with self.subTest(pfad=pfad):
                self.assertEqual(self.client.get(pfad).status_code, 200)


class KatalogLadenTest(TestCase):
    def test_ist_wiederholbar_und_verknuepft_bereichstypen(self):
        from django.core.management import call_command
        from io import StringIO

        call_command("katalog_laden", stdout=StringIO(), stderr=StringIO())
        anzahl = Taetigkeit.objects.count()
        call_command("katalog_laden", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(Taetigkeit.objects.count(), anzahl)

        filter_wechseln = Taetigkeit.objects.get(schluessel="luftfilter-wechseln")
        self.assertEqual(filter_wechseln.standard_intervall_wert, 30)
        self.assertIn(
            "waermepumpe",
            list(filter_wechseln.bereichs_typen.values_list("schluessel", flat=True)),
        )

    def test_alle_katalogeintraege_sind_dreisprachig(self):
        from django.core.management import call_command
        from io import StringIO

        call_command("katalog_laden", stdout=StringIO(), stderr=StringIO())
        for modell in [ObjektTyp, BereichsTyp, Taetigkeit]:
            for eintrag in modell.objects.all():
                with self.subTest(modell=modell.__name__, schluessel=eintrag.schluessel):
                    self.assertTrue(eintrag.name_de and eintrag.name_en and eintrag.name_sv)
