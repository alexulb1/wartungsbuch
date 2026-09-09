"""Tests für Anhänge: Modell, Ablagepfad, Papierkorb."""

import datetime as dt
import shutil
import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

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


def bild(name="foto.jpg", inhalt=b"\xff\xd8\xff\xe0Nicht wirklich JPEG"):
    return SimpleUploadedFile(name, inhalt, content_type="image/jpeg")


class AnhangBestand(TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.ueberschreiben = override_settings(MEDIA_ROOT=self.ordner)
        self.ueberschreiben.enable()
        self.addCleanup(self.ueberschreiben.disable)

        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        self.taetigkeit = Taetigkeit.objects.create(
            schluessel="filter", name_de="Luftfilter wechseln"
        )
        self.objekt = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.bereich = Bereich.objects.create(objekt=self.objekt, typ=bereichs_typ)
        self.aufgabe = Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=self.taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        self.ereignis = Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 3, 12)
        )
        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")


class AblagepfadTest(AnhangBestand):
    """Der abgelegte Name muss ohne Software verständlich sein -- das ist der
    Grund, warum die Dateien überhaupt im Dateisystem liegen."""

    def test_am_ereignis_traegt_datum_und_taetigkeit(self):
        anhang = Anhang.objects.create(
            bereich=self.bereich, ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg"
        )
        pfad = anhang.datei.name
        self.assertTrue(pfad.startswith("haupthaus/"), pfad)
        self.assertIn("2026-03-12", pfad)
        self.assertIn("luftfilter-wechseln", pfad)
        self.assertTrue(pfad.endswith(".jpg"), pfad)

    def test_ohne_ereignis_traegt_beschriftung_und_heutiges_datum(self):
        anhang = Anhang.objects.create(
            bereich=self.bereich,
            datei=SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf"),
            dateiname="a.pdf",
            beschriftung="Wärmepumpe Anleitung",
        )
        self.assertIn("warmepumpe-anleitung", anhang.datei.name)
        self.assertTrue(anhang.datei.name.endswith(".pdf"))

    def test_zwei_anhaenge_kollidieren_nicht(self):
        erster = Anhang.objects.create(
            bereich=self.bereich, ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg"
        )
        zweiter = Anhang.objects.create(
            bereich=self.bereich, ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg"
        )
        self.assertNotEqual(erster.datei.name, zweiter.datei.name)


class ZugehoerigkeitTest(AnhangBestand):
    def test_bereich_wird_aus_dem_ereignis_abgeleitet(self):
        anhang = Anhang(ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg")
        anhang.full_clean()
        anhang.save()
        self.assertEqual(anhang.bereich, self.bereich)

    def test_widerspruechlicher_bereich_wird_beanstandet(self):
        anderer_typ = BereichsTyp.objects.create(schluessel="dach", name_de="Dach")
        anderer = Bereich.objects.create(objekt=self.objekt, typ=anderer_typ)
        anhang = Anhang(
            bereich=anderer, ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg"
        )
        with self.assertRaises(ValidationError):
            anhang.full_clean()


class PapierkorbTest(AnhangBestand):
    """Gelöschtes ist 30 Tage lang zurückholbar -- bei etwas steuerlich
    Relevantem ist das den Ordner wert."""

    def test_geloeschte_datei_wandert_in_den_papierkorb(self):
        anhang = Anhang.objects.create(
            bereich=self.bereich, ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg"
        )
        abgelegt = Path(anhang.datei.path)
        self.assertTrue(abgelegt.exists())

        anhang.delete()

        self.assertFalse(abgelegt.exists())
        papierkorb = list((Path(self.ordner) / "geloescht").glob("*"))
        self.assertEqual(len(papierkorb), 1)

    def test_auch_beim_loeschen_des_ereignisses(self):
        """Django löscht Kaskaden gebündelt und ruft delete() nicht je Zeile
        auf -- deshalb hängt das Verschieben an post_delete."""
        anhang = Anhang.objects.create(
            bereich=self.bereich, ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg"
        )
        abgelegt = Path(anhang.datei.path)

        self.ereignis.delete()

        self.assertFalse(abgelegt.exists())
        self.assertEqual(len(list((Path(self.ordner) / "geloescht").glob("*"))), 1)

    def test_fehlende_datei_stoert_das_loeschen_nicht(self):
        anhang = Anhang.objects.create(
            bereich=self.bereich, ereignis=self.ereignis, datei=bild(), dateiname="foto.jpg"
        )
        Path(anhang.datei.path).unlink()
        anhang.delete()  # darf nicht werfen
        self.assertFalse(Anhang.objects.exists())
