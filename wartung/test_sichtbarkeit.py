"""Tests der Sichtbarkeitsregel (SPEC 2).

Eine Berechtigung, die im Zweifel öffnet, ist keine: Ohne Zuweisung ist nichts
sichtbar. Verwaltungsberechtigte sehen alles.
"""

from django.http import Http404
from django.test import TestCase

from .models import (
    Aufgabe,
    Benutzer,
    Bereich,
    BereichsTyp,
    Einheit,
    Objekt,
    ObjektTyp,
    Taetigkeit,
)
from .sichtbarkeit import (
    aufgabe_oder_404,
    bereich_oder_404,
    darf_sehen,
    sichtbare_objekte,
)


class Bestand(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")

        self.haus = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.sommerhaus = Objekt.objects.create(name="Sommerhaus", typ=objekt_typ)
        self.bereich_haus = Bereich.objects.create(objekt=self.haus, typ=bereichs_typ)
        self.bereich_sommer = Bereich.objects.create(objekt=self.sommerhaus, typ=bereichs_typ)
        self.aufgabe_sommer = Aufgabe.objects.create(
            bereich=self.bereich_sommer,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )

        self.verwaltung = Benutzer.objects.create_user("chef@example.org", is_staff=True)
        self.betreuer = Benutzer.objects.create_user("hilfe@example.org")
        self.betreuer.zugewiesene_objekte.add(self.haus)
        self.fremder = Benutzer.objects.create_user("fremd@example.org")


class SichtbareObjekteTest(Bestand):
    def test_verwaltung_sieht_alles(self):
        self.assertEqual(sichtbare_objekte(self.verwaltung).count(), 2)

    def test_zugewiesener_sieht_nur_seins(self):
        self.assertEqual(list(sichtbare_objekte(self.betreuer)), [self.haus])

    def test_ohne_zuweisung_nichts(self):
        self.assertEqual(list(sichtbare_objekte(self.fremder)), [])

    def test_zuweisung_laesst_sich_entziehen(self):
        self.betreuer.zugewiesene_objekte.remove(self.haus)
        self.assertEqual(list(sichtbare_objekte(self.betreuer)), [])


class DarfSehenTest(Bestand):
    def test_verwaltung_darf_alles(self):
        self.assertTrue(darf_sehen(self.verwaltung, self.sommerhaus))

    def test_zugewiesener_darf_seins(self):
        self.assertTrue(darf_sehen(self.betreuer, self.haus))

    def test_zugewiesener_darf_fremdes_nicht(self):
        self.assertFalse(darf_sehen(self.betreuer, self.sommerhaus))


class HolenUndPruefenTest(Bestand):
    """Holen und Prüfen sind zusammengelegt -- getrennt kann man das Prüfen
    vergessen."""

    def test_bereich_wird_geliefert(self):
        self.assertEqual(bereich_oder_404(self.betreuer, self.bereich_haus.pk), self.bereich_haus)

    def test_fremder_bereich_ergibt_404(self):
        with self.assertRaises(Http404):
            bereich_oder_404(self.betreuer, self.bereich_sommer.pk)

    def test_fremde_aufgabe_ergibt_404(self):
        with self.assertRaises(Http404):
            aufgabe_oder_404(self.betreuer, self.aufgabe_sommer.pk)

    def test_verwaltung_bekommt_auch_fremdes(self):
        self.assertEqual(
            aufgabe_oder_404(self.verwaltung, self.aufgabe_sommer.pk), self.aufgabe_sommer
        )

    def test_unbekannte_nummer_ergibt_404(self):
        with self.assertRaises(Http404):
            bereich_oder_404(self.verwaltung, 999999)
