"""Bereiche tragen ihre Bezeichnung in allen drei Sprachen.

Der Typ kommt aus dem Katalog und war immer schon dreisprachig ("Fassade",
"Facade", "Fasad"). Die Bezeichnung daneben unterscheidet gleichartige Bereiche
voneinander ("Ost", "EG") -- sie stand bisher nur auf Deutsch da und blieb
deshalb auch in der englischen Oberflaeche deutsch.

Fehlt eine Uebersetzung, gilt dieselbe Regel wie im Katalog: lieber der
deutsche Begriff als eine leere Zelle.
"""

import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from .models import Benutzer, Bereich, BereichsTyp, Ereignis, Objekt, ObjektTyp


class Bestand(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(
            schluessel="haus", name_de="Haus", name_en="House", name_sv="Hus"
        )
        self.typ = BereichsTyp.objects.create(
            schluessel="fassade", name_de="Fassade", name_en="Facade", name_sv="Fasad"
        )
        self.objekt = Objekt.objects.create(name="Singenberg", typ=objekt_typ)
        self.bereich = Bereich.objects.create(
            objekt=self.objekt,
            typ=self.typ,
            bezeichnung_de="Ost",
            bezeichnung_en="East",
            bezeichnung_sv="Öster",
        )


class BezeichnungTest(Bestand):
    def test_deutsch(self):
        with translation.override("de"):
            self.assertEqual(str(self.bereich), "Fassade Ost")

    def test_englisch(self):
        with translation.override("en"):
            self.assertEqual(str(self.bereich), "Facade East")

    def test_schwedisch(self):
        with translation.override("sv"):
            self.assertEqual(str(self.bereich), "Fasad Öster")

    def test_fehlende_uebersetzung_faellt_auf_deutsch_zurueck(self):
        bereich = Bereich.objects.create(objekt=self.objekt, typ=self.typ, bezeichnung_de="Nord")
        with translation.override("en"):
            self.assertEqual(str(bereich), "Facade Nord")

    def test_ohne_bezeichnung_bleibt_der_typ_allein(self):
        bereich = Bereich.objects.create(objekt=self.objekt, typ=self.typ)
        with translation.override("en"):
            self.assertEqual(str(bereich), "Facade")

    def test_die_sprache_laesst_sich_ausdruecklich_angeben(self):
        self.assertEqual(self.bereich.bezeichnung_in("sv"), "Öster")
        self.assertEqual(self.bereich.bezeichnung_in(None), "Ost")

    def test_die_reihenfolge_richtet_sich_nach_dem_deutschen(self):
        """Sonst stünde dieselbe Liste je nach Anzeigesprache anders da."""
        Bereich.objects.create(
            objekt=self.objekt, typ=self.typ, bezeichnung_de="Alt", bezeichnung_en="Zulu"
        )
        with translation.override("en"):
            bezeichnungen = [b.bezeichnung for b in Bereich.objects.filter(objekt=self.objekt)]
        self.assertEqual(bezeichnungen, ["Zulu", "East"])  # Alt vor Ost


class OberflaecheTest(Bestand):
    def setUp(self):
        super().setUp()
        self.benutzer = Benutzer.objects.create_user(
            "ich@example.org", name="Alex", sprache="en"
        )
        self.benutzer.zugewiesene_objekte.add(self.objekt)
        self.client.force_login(self.benutzer)

    def test_die_bereichsseite_zeigt_die_uebersetzung(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich.pk]))
        self.assertContains(antwort, "Facade East")

    def test_der_nachweis_zeigt_die_uebersetzung(self):
        Ereignis.objects.create(
            bereich=self.bereich, beschreibung="Cleaned", datum=dt.date(2026, 7, 18)
        )
        antwort = self.client.get(reverse("wartung:nachweis", args=[self.objekt.pk]))
        self.assertContains(antwort, "Facade East")


class VerwaltungTest(Bestand):
    """Wer einen Bereich anlegt, muss die Übersetzungen eintragen können."""

    def setUp(self):
        super().setUp()
        chef = Benutzer.objects.create_user("chef@example.org", name="Chef")
        chef.is_staff = True
        chef.is_superuser = True
        chef.save()
        self.client.force_login(chef)

    def test_die_objektseite_bietet_alle_drei_felder(self):
        antwort = self.client.get(reverse("admin:wartung_objekt_change", args=[self.objekt.pk]))
        for feld in ("bezeichnung_de", "bezeichnung_en", "bezeichnung_sv"):
            with self.subTest(feld=feld):
                self.assertContains(antwort, feld)

    def test_die_bereichsseite_bietet_alle_drei_felder(self):
        antwort = self.client.get(reverse("admin:wartung_bereich_change", args=[self.bereich.pk]))
        for feld in ("bezeichnung_de", "bezeichnung_en", "bezeichnung_sv"):
            with self.subTest(feld=feld):
                self.assertContains(antwort, feld)
