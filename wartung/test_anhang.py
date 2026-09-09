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


class DateipruefungTest(TestCase):
    def test_zu_grosse_datei_wird_abgewiesen(self):
        from .dateipruefung import pruefe_datei
        from .models.anhang import HOECHSTGROESSE

        zu_gross = SimpleUploadedFile(
            "gross.jpg", b"x" * (HOECHSTGROESSE + 1), content_type="image/jpeg"
        )
        with self.assertRaises(ValidationError) as fehler:
            pruefe_datei(zu_gross)
        self.assertIn("25", str(fehler.exception))

    def test_unerlaubter_typ_wird_abgewiesen(self):
        from .dateipruefung import pruefe_datei

        schadhaft = SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            pruefe_datei(schadhaft)

    def test_bild_und_pdf_gehen_durch(self):
        from .dateipruefung import pruefe_datei

        pruefe_datei(SimpleUploadedFile("a.jpg", b"x", content_type="image/jpeg"))
        pruefe_datei(SimpleUploadedFile("a.pdf", b"%PDF", content_type="application/pdf"))
        pruefe_datei(SimpleUploadedFile("a.heic", b"x", content_type="image/heic"))

    def test_ohne_typ_entscheidet_die_endung(self):
        """Manche Browser schicken application/octet-stream."""
        from .dateipruefung import pruefe_datei

        pruefe_datei(
            SimpleUploadedFile("a.jpg", b"x", content_type="application/octet-stream")
        )
        with self.assertRaises(ValidationError):
            pruefe_datei(
                SimpleUploadedFile("a.exe", b"x", content_type="application/octet-stream")
            )


class VorschauTest(TestCase):
    def echtes_bild(self, groesse=(2400, 1800), format="JPEG", name="foto.jpg"):
        from io import BytesIO

        from PIL import Image

        puffer = BytesIO()
        Image.new("RGB", groesse, (120, 140, 130)).save(puffer, format=format)
        return SimpleUploadedFile(name, puffer.getvalue(), content_type=f"image/{format.lower()}")

    def test_grosses_bild_wird_verkleinert(self):
        from PIL import Image

        from .vorschau import VORSCHAU_KANTE, vorschau_erzeugen

        ergebnis = vorschau_erzeugen(self.echtes_bild())
        self.assertIsNotNone(ergebnis)
        with Image.open(ergebnis) as bild:
            self.assertEqual(max(bild.size), VORSCHAU_KANTE)

    def test_kleines_bild_wird_nicht_vergroessert(self):
        from PIL import Image

        from .vorschau import vorschau_erzeugen

        ergebnis = vorschau_erzeugen(self.echtes_bild(groesse=(400, 300)))
        with Image.open(ergebnis) as bild:
            self.assertEqual(bild.size, (400, 300))

    def test_vorschau_traegt_einen_namen(self):
        """Ohne Namen lässt sich die Datei keinem Dateifeld zuweisen."""
        from .vorschau import vorschau_erzeugen

        self.assertTrue(vorschau_erzeugen(self.echtes_bild()).name)

    def test_pdf_bekommt_keine_vorschau(self):
        from .vorschau import vorschau_erzeugen

        self.assertIsNone(
            vorschau_erzeugen(
                SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf")
            )
        )

    def test_unlesbares_bild_bekommt_keine_vorschau(self):
        """HEIC kann Pillow ohne Zusatzpaket nicht -- die Datei bleibt trotzdem
        erhalten, nur die Vorschau fehlt."""
        from .vorschau import vorschau_erzeugen

        self.assertIsNone(
            vorschau_erzeugen(
                SimpleUploadedFile("a.heic", b"nicht wirklich HEIC", content_type="image/heic")
            )
        )
