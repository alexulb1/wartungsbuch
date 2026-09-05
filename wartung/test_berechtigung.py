"""Wirkung der Berechtigung an den Ansichten (SPEC 2)."""

import datetime as dt

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
)


class ZweiObjekte(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")

        self.haus = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.sommerhaus = Objekt.objects.create(name="Sommerhaus", typ=objekt_typ)

        self.bereich_haus = Bereich.objects.create(objekt=self.haus, typ=bereichs_typ)
        self.bereich_sommer = Bereich.objects.create(objekt=self.sommerhaus, typ=bereichs_typ)

        self.aufgabe_haus = Aufgabe.objects.create(
            bereich=self.bereich_haus,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        self.aufgabe_sommer = Aufgabe.objects.create(
            bereich=self.bereich_sommer,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        Ereignis.objects.create(
            bereich=self.bereich_sommer,
            beschreibung="Sommerhaus renoviert",
            datum=dt.date(2026, 1, 1),
        )

        self.betreuer = Benutzer.objects.create_user("hilfe@example.org", name="Hilfe")
        self.betreuer.zugewiesene_objekte.add(self.haus)
        self.client.force_login(self.betreuer)


class DashboardBerechtigungTest(ZweiObjekte):
    def test_zeigt_nur_zugewiesenes(self):
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "Haupthaus")
        self.assertNotContains(antwort, "Sommerhaus")

    def test_ohne_zuweisung_leer(self):
        self.betreuer.zugewiesene_objekte.clear()
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertNotContains(antwort, "Haupthaus")
        self.assertNotContains(antwort, "Sommerhaus")


class DetailseitenTest(ZweiObjekte):
    def test_fremder_bereich_ergibt_404(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich_sommer.pk]))
        self.assertEqual(antwort.status_code, 404)

    def test_eigener_bereich_ist_erreichbar(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich_haus.pk]))
        self.assertEqual(antwort.status_code, 200)

    def test_fremde_aufgabe_laesst_sich_nicht_abhaken(self):
        antwort = self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe_sommer.pk]), {"datum": "2026-03-12"}
        )
        self.assertEqual(antwort.status_code, 404)
        self.assertFalse(Ereignis.objects.filter(aufgabe=self.aufgabe_sommer).exists())

    def test_fremder_bereich_nimmt_kein_ereignis_an(self):
        antwort = self.client.post(
            reverse("wartung:ereignis_neu", args=[self.bereich_sommer.pk]),
            {"datum": "2026-03-12", "beschreibung": "Eingeschmuggelt"},
        )
        self.assertEqual(antwort.status_code, 404)
        self.assertFalse(Ereignis.objects.filter(beschreibung="Eingeschmuggelt").exists())

    def test_fremder_bereich_nimmt_keine_katalogaufgaben(self):
        antwort = self.client.get(
            reverse("wartung:aufgaben_ergaenzen", args=[self.bereich_sommer.pk])
        )
        self.assertEqual(antwort.status_code, 404)


class AusgabenTest(ZweiObjekte):
    def test_csv_enthaelt_nur_zugewiesenes(self):
        inhalt = self.client.get(reverse("wartung:export_csv")).content.decode("utf-8-sig")
        self.assertNotIn("Sommerhaus", inhalt)

    def test_kalender_enthaelt_nur_zugewiesenes(self):
        antwort = self.client.get(
            reverse("wartung:kalender", args=[self.betreuer.kalender_schluessel])
        )
        text = antwort.content.decode()
        self.assertIn("Haupthaus", text)
        self.assertNotIn("Sommerhaus", text)


class VerwaltungTest(ZweiObjekte):
    def setUp(self):
        super().setUp()
        self.chef = Benutzer.objects.create_user("chef@example.org", is_staff=True)
        self.client.force_login(self.chef)

    def test_verwaltung_sieht_beides(self):
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "Haupthaus")
        self.assertContains(antwort, "Sommerhaus")

    def test_verwaltung_erreicht_jeden_bereich(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich_sommer.pk]))
        self.assertEqual(antwort.status_code, 200)
