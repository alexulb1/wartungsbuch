"""Tests für Hochladen, Ausliefern und Löschen von Anhängen."""

import datetime as dt
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    Anhang,
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


def echtes_bild(name="foto.jpg", groesse=(1600, 1200)):
    from PIL import Image

    puffer = BytesIO()
    Image.new("RGB", groesse, (120, 140, 130)).save(puffer, format="JPEG")
    return SimpleUploadedFile(name, puffer.getvalue(), content_type="image/jpeg")


class AnhangOberflaeche(TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.ueberschreiben = override_settings(MEDIA_ROOT=self.ordner)
        self.ueberschreiben.enable()
        self.addCleanup(self.ueberschreiben.disable)

        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")

        self.objekt = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.fremdes = Objekt.objects.create(name="Sommerhaus", typ=objekt_typ)
        self.bereich = Bereich.objects.create(objekt=self.objekt, typ=bereichs_typ)
        self.fremder_bereich = Bereich.objects.create(objekt=self.fremdes, typ=bereichs_typ)
        self.aufgabe = Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )

        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.benutzer.zugewiesene_objekte.add(self.objekt)
        self.client.force_login(self.benutzer)


class HochladenBeimAbhakenTest(AnhangOberflaeche):
    def test_foto_wird_mit_abgespeichert(self):
        antwort = self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]),
            {"datum": "2026-03-12", "anhaenge": [echtes_bild()]},
        )
        self.assertEqual(antwort.status_code, 302)
        anhang = Anhang.objects.get()
        self.assertEqual(anhang.bereich, self.bereich)
        self.assertEqual(anhang.ereignis, Ereignis.objects.get())
        self.assertEqual(anhang.dateiname, "foto.jpg")
        self.assertEqual(anhang.hochgeladen_von, self.benutzer)

    def test_mehrere_dateien_auf_einmal(self):
        self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]),
            {
                "datum": "2026-03-12",
                "anhaenge": [echtes_bild("eins.jpg"), echtes_bild("zwei.jpg")],
            },
        )
        self.assertEqual(Anhang.objects.count(), 2)

    def test_vorschau_wird_erzeugt(self):
        self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]),
            {"datum": "2026-03-12", "anhaenge": [echtes_bild()]},
        )
        self.assertTrue(Anhang.objects.get().vorschau)

    def test_unerlaubte_datei_verhindert_den_ganzen_vorgang(self):
        """Kein halbes Ergebnis: Wird die Datei abgewiesen, entsteht auch kein
        Ereignis -- sonst stünde eine Erledigung ohne den Beleg da, den man
        eigentlich anhängen wollte."""
        antwort = self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]),
            {
                "datum": "2026-03-12",
                "anhaenge": [
                    SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")
                ],
            },
        )
        self.assertEqual(antwort.status_code, 200)
        self.assertFalse(Ereignis.objects.exists())
        self.assertFalse(Anhang.objects.exists())

    def test_ohne_datei_bleibt_alles_wie_bisher(self):
        antwort = self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]), {"datum": "2026-03-12"}
        )
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(Ereignis.objects.count(), 1)
        self.assertFalse(Anhang.objects.exists())


class KeinUploadAusDerMailTest(AnhangOberflaeche):
    """Der Abhak-Link darf genau eine Aufgabe abhaken und sonst nichts.

    Ein Datei-Upload daran wäre unangemeldeter Schreibzugriff auf den Speicher.
    Weil die Seite dasselbe Formular benutzt, muss das Feld dort ausdrücklich
    entfernt werden -- sonst stünde dort ein Feld, das nichts tut.
    """

    def setUp(self):
        super().setUp()
        from .models import Zugangsmarke, Zweck

        _, self.roh = Zugangsmarke.objects.anlegen(
            Zweck.ERLEDIGUNG, self.benutzer, aufgabe=self.aufgabe
        )
        self.client.logout()

    def test_die_seite_zeigt_kein_dateifeld(self):
        antwort = self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertEqual(antwort.status_code, 200)
        self.assertNotContains(antwort, 'type="file"')

    def test_mitgeschickte_dateien_werden_nicht_abgelegt(self):
        antwort = self.client.post(
            reverse("wartung:erledigt_mit_marke", args=[self.roh]),
            {"datum": "2026-03-12", "anhaenge": [echtes_bild()]},
        )
        self.assertEqual(antwort.status_code, 200)
        self.assertTrue(Ereignis.objects.exists())
        self.assertFalse(Anhang.objects.exists())


class HochladenBeimFreienEreignisTest(AnhangOberflaeche):
    def test_foto_am_einmaligen_vorgang(self):
        self.client.post(
            reverse("wartung:ereignis_neu", args=[self.bereich.pk]),
            {"datum": "2019-06-20", "beschreibung": "Bad renoviert", "anhaenge": [echtes_bild()]},
        )
        anhang = Anhang.objects.get()
        self.assertEqual(anhang.ereignis.beschreibung, "Bad renoviert")


class AusliefernTest(AnhangOberflaeche):
    def setUp(self):
        super().setUp()
        from .anhaenge import anhaenge_speichern

        self.ereignis = Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 3, 12)
        )
        self.anhang = anhaenge_speichern(
            [echtes_bild("typenschild.jpg")], self.bereich, self.benutzer, self.ereignis
        )[0]
        self.fremder = anhaenge_speichern(
            [echtes_bild("fremd.jpg")], self.fremder_bereich, self.benutzer
        )[0]

    def test_eigener_anhang_wird_ausgeliefert(self):
        antwort = self.client.get(reverse("wartung:anhang", args=[self.anhang.kennung]))
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort["Content-Type"], "image/jpeg")

    def test_der_urspruengliche_dateiname_steht_im_download(self):
        antwort = self.client.get(reverse("wartung:anhang", args=[self.anhang.kennung]))
        self.assertIn("typenschild.jpg", antwort["Content-Disposition"])

    def test_vorschau_wird_ausgeliefert(self):
        antwort = self.client.get(reverse("wartung:anhang_vorschau", args=[self.anhang.kennung]))
        self.assertEqual(antwort.status_code, 200)

    def test_fremder_anhang_ergibt_404(self):
        antwort = self.client.get(reverse("wartung:anhang", args=[self.fremder.kennung]))
        self.assertEqual(antwort.status_code, 404)

    def test_fremde_vorschau_ergibt_404(self):
        antwort = self.client.get(reverse("wartung:anhang_vorschau", args=[self.fremder.kennung]))
        self.assertEqual(antwort.status_code, 404)

    def test_ohne_anmeldung_kein_zugriff(self):
        self.client.logout()
        antwort = self.client.get(reverse("wartung:anhang", args=[self.anhang.kennung]))
        self.assertIn(antwort.status_code, (302, 404))

    def test_erfundene_kennung_ergibt_404(self):
        import uuid

        antwort = self.client.get(reverse("wartung:anhang", args=[uuid.uuid4()]))
        self.assertEqual(antwort.status_code, 404)

    def test_fehlende_vorschau_ergibt_404(self):
        from .anhaenge import anhaenge_speichern

        ohne = anhaenge_speichern(
            [SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf")],
            self.bereich,
            self.benutzer,
        )[0]
        antwort = self.client.get(reverse("wartung:anhang_vorschau", args=[ohne.kennung]))
        self.assertEqual(antwort.status_code, 404)


class BereichsseiteTest(AnhangOberflaeche):
    def setUp(self):
        super().setUp()
        from .anhaenge import anhaenge_speichern

        self.ereignis = Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 3, 12)
        )
        self.am_ereignis = anhaenge_speichern(
            [echtes_bild("typenschild.jpg")], self.bereich, self.benutzer, self.ereignis
        )[0]
        self.unterlage = anhaenge_speichern(
            [SimpleUploadedFile("anleitung.pdf", b"%PDF-1.4", content_type="application/pdf")],
            self.bereich,
            self.benutzer,
        )[0]
        self.unterlage.beschriftung = "Bedienungsanleitung"
        self.unterlage.save()

    def test_unterlagen_stehen_in_einem_eigenen_abschnitt(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich.pk]))
        self.assertContains(antwort, "Unterlagen")
        self.assertContains(antwort, "Bedienungsanleitung")

    def test_anhang_am_ereignis_erscheint_in_der_historie(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich.pk]))
        self.assertContains(
            antwort, reverse("wartung:anhang_vorschau", args=[self.am_ereignis.kennung])
        )

    def test_nachtragen_legt_eine_unterlage_an(self):
        antwort = self.client.post(
            reverse("wartung:anhang_neu", args=[self.bereich.pk]),
            {"beschriftung": "Datenblatt", "anhaenge": [echtes_bild("datenblatt.jpg")]},
        )
        self.assertEqual(antwort.status_code, 302)
        neu = Anhang.objects.get(beschriftung="Datenblatt")
        self.assertIsNone(neu.ereignis)
        self.assertEqual(neu.bereich, self.bereich)

    def test_nachtragen_an_fremdem_bereich_ergibt_404(self):
        antwort = self.client.post(
            reverse("wartung:anhang_neu", args=[self.fremder_bereich.pk]),
            {"beschriftung": "Eingeschmuggelt", "anhaenge": [echtes_bild()]},
        )
        self.assertEqual(antwort.status_code, 404)
        self.assertFalse(Anhang.objects.filter(beschriftung="Eingeschmuggelt").exists())

    def test_loeschen_entfernt_den_eintrag_und_verschiebt_die_datei(self):
        abgelegt = Path(self.am_ereignis.datei.path)
        antwort = self.client.post(
            reverse("wartung:anhang_loeschen", args=[self.am_ereignis.kennung])
        )
        self.assertEqual(antwort.status_code, 302)
        self.assertFalse(Anhang.objects.filter(pk=self.am_ereignis.pk).exists())
        self.assertFalse(abgelegt.exists())
        self.assertTrue(list((Path(self.ordner) / "geloescht").glob("*")))

    def test_blosser_aufruf_loescht_nicht(self):
        """Ein Löschen darf nie an einem GET hängen -- Vorschauen und Scanner
        rufen Links ab."""
        antwort = self.client.get(
            reverse("wartung:anhang_loeschen", args=[self.am_ereignis.kennung])
        )
        self.assertIn(antwort.status_code, (200, 405))
        self.assertTrue(Anhang.objects.filter(pk=self.am_ereignis.pk).exists())

    def test_fremden_anhang_kann_man_nicht_loeschen(self):
        from .anhaenge import anhaenge_speichern

        fremder = anhaenge_speichern(
            [echtes_bild("fremd.jpg")], self.fremder_bereich, self.benutzer
        )[0]
        antwort = self.client.post(reverse("wartung:anhang_loeschen", args=[fremder.kennung]))
        self.assertEqual(antwort.status_code, 404)
        self.assertTrue(Anhang.objects.filter(pk=fremder.pk).exists())


class BeschriftungImDateinamenTest(AnhangOberflaeche):
    """Die Beschriftung muss vor dem Ablegen feststehen.

    Wird sie erst danach gesetzt, steht der Pfad schon fest und die Datei heißt
    nach dem Bereich statt nach dem, was sie zeigt -- die Ablage wäre dann nur
    halb selbsterklärend.
    """

    def test_die_beschriftung_steht_im_dateinamen(self):
        self.client.post(
            reverse("wartung:anhang_neu", args=[self.bereich.pk]),
            {
                "beschriftung": "Bedienungsanleitung Vaillant",
                "anhaenge": [
                    SimpleUploadedFile("x.pdf", b"%PDF-1.4", content_type="application/pdf")
                ],
            },
        )
        anhang = Anhang.objects.get()
        self.assertIn("bedienungsanleitung-vaillant", anhang.datei.name)

    def test_ohne_beschriftung_tritt_der_bereich_ein(self):
        self.client.post(
            reverse("wartung:anhang_neu", args=[self.bereich.pk]),
            {
                "beschriftung": "",
                "anhaenge": [
                    SimpleUploadedFile("x.pdf", b"%PDF-1.4", content_type="application/pdf")
                ],
            },
        )
        self.assertIn("warmepumpe", Anhang.objects.get().datei.name)
