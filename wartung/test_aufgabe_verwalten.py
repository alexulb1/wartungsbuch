"""Aufgaben aus der Anwendung heraus stilllegen und löschen."""

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


class Bestand(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")

        self.objekt = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.fremdes = Objekt.objects.create(name="Sommerhaus", typ=objekt_typ)
        self.bereich = Bereich.objects.create(objekt=self.objekt, typ=bereichs_typ)
        fremder_bereich = Bereich.objects.create(objekt=self.fremdes, typ=bereichs_typ)

        self.aufgabe = Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        self.fremde = Aufgabe.objects.create(
            bereich=fremder_bereich,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        self.ereignis = Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 3, 12)
        )

        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.benutzer.zugewiesene_objekte.add(self.objekt)
        self.client.force_login(self.benutzer)


class StilllegenTest(Bestand):
    """Die sanfte Fassung: verschwindet aus der Planung, bleibt erhalten."""

    def test_stilllegen_nimmt_die_aufgabe_aus_der_planung(self):
        antwort = self.client.post(reverse("wartung:aufgabe_stilllegen", args=[self.aufgabe.pk]))
        self.assertEqual(antwort.status_code, 302)
        self.aufgabe.refresh_from_db()
        self.assertFalse(self.aufgabe.aktiv)

    def test_stillgelegte_aufgabe_erscheint_nicht_mehr_im_dashboard(self):
        self.client.post(reverse("wartung:aufgabe_stilllegen", args=[self.aufgabe.pk]))
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertNotContains(antwort, "Luftfilter wechseln")

    def test_wieder_aufnehmen(self):
        self.client.post(reverse("wartung:aufgabe_stilllegen", args=[self.aufgabe.pk]))
        self.client.post(reverse("wartung:aufgabe_aufnehmen", args=[self.aufgabe.pk]))
        self.aufgabe.refresh_from_db()
        self.assertTrue(self.aufgabe.aktiv)

    def test_stillgelegte_steht_weiterhin_auf_der_bereichsseite(self):
        """Sonst könnte man sie nie zurückholen."""
        self.client.post(reverse("wartung:aufgabe_stilllegen", args=[self.aufgabe.pk]))
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich.pk]))
        self.assertContains(antwort, "Luftfilter wechseln")
        self.assertContains(antwort, "stillgelegt")

    def test_blosser_aufruf_legt_nicht_still(self):
        antwort = self.client.get(reverse("wartung:aufgabe_stilllegen", args=[self.aufgabe.pk]))
        self.assertIn(antwort.status_code, (200, 405))
        self.aufgabe.refresh_from_db()
        self.assertTrue(self.aufgabe.aktiv)

    def test_fremde_aufgabe_ergibt_404(self):
        antwort = self.client.post(reverse("wartung:aufgabe_stilllegen", args=[self.fremde.pk]))
        self.assertEqual(antwort.status_code, 404)
        self.fremde.refresh_from_db()
        self.assertTrue(self.fremde.aktiv)


class LoeschenTest(Bestand):
    def test_die_rueckfrage_nennt_was_dranhaengt(self):
        antwort = self.client.get(reverse("wartung:aufgabe_loeschen", args=[self.aufgabe.pk]))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Luftfilter wechseln")
        self.assertContains(antwort, "30")

    def test_die_rueckfrage_nennt_die_zahl_der_ereignisse(self):
        """Man soll wissen, was stehenbleibt, bevor man entscheidet."""
        Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 2, 1)
        )
        antwort = self.client.get(reverse("wartung:aufgabe_loeschen", args=[self.aufgabe.pk]))
        self.assertContains(antwort, "2")

    def test_blosser_aufruf_loescht_nicht(self):
        self.client.get(reverse("wartung:aufgabe_loeschen", args=[self.aufgabe.pk]))
        self.assertTrue(Aufgabe.objects.filter(pk=self.aufgabe.pk).exists())

    def test_absenden_loescht(self):
        antwort = self.client.post(reverse("wartung:aufgabe_loeschen", args=[self.aufgabe.pk]))
        self.assertEqual(antwort.status_code, 302)
        self.assertFalse(Aufgabe.objects.filter(pk=self.aufgabe.pk).exists())

    def test_die_ereignisse_bleiben_stehen(self):
        """Die Historie ist die Wahrheit und wird nicht umgeschrieben."""
        self.client.post(reverse("wartung:aufgabe_loeschen", args=[self.aufgabe.pk]))
        uebrig = Ereignis.objects.get(pk=self.ereignis.pk)
        self.assertIsNone(uebrig.aufgabe)
        self.assertEqual(uebrig.bezeichnung, "Luftfilter wechseln")

    def test_fremde_aufgabe_ergibt_404(self):
        antwort = self.client.post(reverse("wartung:aufgabe_loeschen", args=[self.fremde.pk]))
        self.assertEqual(antwort.status_code, 404)
        self.assertTrue(Aufgabe.objects.filter(pk=self.fremde.pk).exists())
