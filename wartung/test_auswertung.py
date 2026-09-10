"""Wartungsnachweis und Jahresvorschau.

Der Nachweis ist das Dokument, für das dieses Programm existiert: was an einem
Objekt geschah, zusammenhängend und weitergebbar. Die Vorschau ist sein
Gegenstück nach vorn.

Beide sind zum Ausdrucken gedacht -- der Browser macht daraus die PDF-Datei.
Eine PDF-Bibliothek wäre eine Abhängigkeit auf zehn Jahre für ein Ergebnis,
das der Browser ohnehin liefert.
"""

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
        wp_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe", sortierung=10)
        dach_typ = BereichsTyp.objects.create(schluessel="dach", name_de="Dach", sortierung=20)
        self.filter = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")
        rinne = Taetigkeit.objects.create(schluessel="rinne", name_de="Dachrinne reinigen")

        self.haus = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.sommerhaus = Objekt.objects.create(name="Sommerhaus", typ=objekt_typ)

        self.wp = Bereich.objects.create(objekt=self.haus, typ=wp_typ)
        self.dach = Bereich.objects.create(objekt=self.haus, typ=dach_typ)
        self.fremder = Bereich.objects.create(objekt=self.sommerhaus, typ=wp_typ)

        self.aufgabe = Aufgabe.objects.create(
            bereich=self.wp,
            taetigkeit=self.filter,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        Aufgabe.objects.create(
            bereich=self.dach, taetigkeit=rinne, intervall_wert=1, intervall_einheit=Einheit.JAHRE
        )

        Ereignis.objects.create(
            bereich=self.wp,
            aufgabe=self.aufgabe,
            datum=dt.date(2025, 5, 4),
            kosten=45,
            ausgefuehrt_von="Fa. Berg",
        )
        Ereignis.objects.create(
            bereich=self.wp, aufgabe=self.aufgabe, datum=dt.date(2026, 3, 12), kosten=55
        )
        Ereignis.objects.create(
            bereich=self.dach, beschreibung="Ziegel gerichtet", datum=dt.date(2026, 6, 1), kosten=300
        )
        Ereignis.objects.create(
            bereich=self.fremder, beschreibung="Fremdvorgang", datum=dt.date(2026, 3, 12)
        )

        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.benutzer.zugewiesene_objekte.add(self.haus)
        self.client.force_login(self.benutzer)


class NachweisTest(Bestand):
    def adresse(self, objekt=None, **filter):
        ziel = reverse("wartung:nachweis", args=[(objekt or self.haus).pk])
        if filter:
            ziel += "?" + "&".join(f"{k}={v}" for k, v in filter.items())
        return ziel

    def test_erreichbar_fuer_das_eigene_objekt(self):
        self.assertEqual(self.client.get(self.adresse()).status_code, 200)

    def test_fremdes_objekt_ergibt_404(self):
        antwort = self.client.get(self.adresse(self.sommerhaus))
        self.assertEqual(antwort.status_code, 404)
        self.assertNotContains(antwort, "Fremdvorgang", status_code=404)

    def test_enthaelt_alle_vorgaenge_des_objekts(self):
        antwort = self.client.get(self.adresse())
        self.assertContains(antwort, "Luftfilter wechseln")
        self.assertContains(antwort, "Ziegel gerichtet")

    def test_enthaelt_keine_fremden_vorgaenge(self):
        self.assertNotContains(self.client.get(self.adresse()), "Fremdvorgang")

    def test_nach_bereich_gegliedert(self):
        """Wer das Dokument bekommt, fragt nach dem Dach, nicht nach dem März."""
        inhalt = self.client.get(self.adresse()).content.decode()
        self.assertLess(inhalt.index("Wärmepumpe"), inhalt.index("Dach"))
        self.assertLess(inhalt.index("Dach"), inhalt.index("Ziegel gerichtet"))

    def test_nennt_die_gesamtkosten(self):
        antwort = self.client.get(self.adresse())
        self.assertContains(antwort, "400")  # 45 + 55 + 300

    def test_nennt_die_zahl_der_vorgaenge(self):
        self.assertContains(self.client.get(self.adresse()), "3")

    def test_zeitraum_von_grenzt_ein(self):
        antwort = self.client.get(self.adresse(von="2026-01-01"))
        self.assertContains(antwort, "Ziegel gerichtet")
        self.assertNotContains(antwort, "Fa. Berg")

    def test_zeitraum_bis_grenzt_ein(self):
        antwort = self.client.get(self.adresse(bis="2025-12-31"))
        self.assertContains(antwort, "Fa. Berg")
        self.assertNotContains(antwort, "Ziegel gerichtet")

    def test_gesamtkosten_folgen_dem_zeitraum(self):
        antwort = self.client.get(self.adresse(von="2026-01-01"))
        self.assertContains(antwort, "355")  # 55 + 300

    def test_unsinniger_zeitraum_wird_übergangen(self):
        self.assertEqual(self.client.get(self.adresse(von="unfug")).status_code, 200)

    def test_nennt_die_namen_der_anhaenge(self):
        import shutil
        import tempfile
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from PIL import Image

        ordner = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, ordner, True)
        with override_settings(MEDIA_ROOT=ordner):
            from .anhaenge import anhaenge_speichern

            puffer = BytesIO()
            Image.new("RGB", (80, 60)).save(puffer, format="JPEG")
            anhaenge_speichern(
                [SimpleUploadedFile("typenschild.jpg", puffer.getvalue(), content_type="image/jpeg")],
                self.wp,
                self.benutzer,
                Ereignis.objects.filter(bereich=self.wp).first(),
            )
            antwort = self.client.get(self.adresse())
        self.assertContains(antwort, "typenschild.jpg")


class VorschauTest(Bestand):
    def adresse(self, **filter):
        ziel = reverse("wartung:jahresvorschau")
        if filter:
            ziel += "?" + "&".join(f"{k}={v}" for k, v in filter.items())
        return ziel

    def test_erreichbar(self):
        self.assertEqual(self.client.get(self.adresse()).status_code, 200)

    def test_zeigt_nur_zugewiesene_objekte(self):
        aufgabe = Aufgabe.objects.create(
            bereich=self.fremder,
            taetigkeit=self.filter,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        Ereignis.objects.create(bereich=self.fremder, aufgabe=aufgabe, datum=dt.date(2026, 3, 1))
        antwort = self.client.get(self.adresse(stichtag="2026-04-01"))
        self.assertContains(antwort, "Haupthaus")
        self.assertNotContains(antwort, "Sommerhaus")

    def test_ueberfaelliges_steht_in_einem_eigenen_block(self):
        antwort = self.client.get(self.adresse(stichtag="2027-01-15"))
        self.assertContains(antwort, "überfällig")

    def test_reicht_zwoelf_monate_weit(self):
        """Was danach kommt, gehört nicht in eine Jahresvorschau."""
        Aufgabe.objects.create(
            bereich=self.dach,
            taetigkeit=Taetigkeit.objects.create(schluessel="fern", name_de="Fassade streichen"),
            intervall_wert=10,
            intervall_einheit=Einheit.JAHRE,
        )
        Ereignis.objects.create(
            bereich=self.dach,
            aufgabe=Aufgabe.objects.get(taetigkeit__schluessel="fern"),
            datum=dt.date(2026, 6, 1),
        )
        antwort = self.client.get(self.adresse(stichtag="2026-06-02"))
        self.assertNotContains(antwort, "Fassade streichen")

    def test_ohne_anmeldung_kein_zugriff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.adresse()).status_code, 302)
