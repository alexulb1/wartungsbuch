"""Einzelne Ereignisse aus der Anwendung heraus löschen.

Der heikelste Löschvorgang der Anwendung: Ein Ereignis ist die einzige Wahrheit,
und weil die Fälligkeit daraus berechnet wird, verschiebt sein Verschwinden
rückwirkend den nächsten Termin. Deshalb die Rückfrage, und deshalb rechnet sie
die Folge vorher aus.
"""

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


def echtes_bild(name="foto.jpg"):
    from PIL import Image

    puffer = BytesIO()
    Image.new("RGB", (800, 600), (120, 140, 130)).save(puffer, format="JPEG")
    return SimpleUploadedFile(name, puffer.getvalue(), content_type="image/jpeg")


class Bestand(TestCase):
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
        fremder_bereich = Bereich.objects.create(objekt=self.fremdes, typ=bereichs_typ)

        self.aufgabe = Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        self.aelter = Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 1, 16)
        )
        self.juengstes = Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 3, 12)
        )
        self.fremdes_ereignis = Ereignis.objects.create(
            bereich=fremder_bereich, beschreibung="Fremd", datum=dt.date(2026, 3, 12)
        )

        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.benutzer.zugewiesene_objekte.add(self.objekt)
        self.client.force_login(self.benutzer)

    def adresse(self, ereignis):
        return reverse("wartung:ereignis_loeschen", args=[ereignis.pk])


class RueckfrageTest(Bestand):
    def test_nennt_datum_und_bezeichnung(self):
        antwort = self.client.get(self.adresse(self.juengstes))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Luftfilter wechseln")
        self.assertContains(antwort, "12.03.2026")

    def test_nennt_die_neue_faelligkeit(self):
        """Nach dem Löschen der jüngsten Erledigung rechnet die Anwendung ab
        der davorliegenden -- das kann schlagartig überfällig bedeuten."""
        antwort = self.client.get(self.adresse(self.juengstes))
        # 16.01.2026 + 30 Tage = 15.02.2026
        self.assertContains(antwort, "15.02.2026")

    def test_nennt_die_zahl_der_anhaenge(self):
        from .anhaenge import anhaenge_speichern

        anhaenge_speichern([echtes_bild()], self.bereich, self.benutzer, self.juengstes)
        antwort = self.client.get(self.adresse(self.juengstes))
        self.assertContains(antwort, "1")

    def test_ohne_aufgabe_keine_faelligkeitsaussage(self):
        einmalig = Ereignis.objects.create(
            bereich=self.bereich, beschreibung="Bad renoviert", datum=dt.date(2019, 6, 1)
        )
        antwort = self.client.get(self.adresse(einmalig))
        self.assertContains(antwort, "Bad renoviert")
        self.assertNotContains(antwort, "Fälligkeit")

    def test_blosser_aufruf_loescht_nicht(self):
        self.client.get(self.adresse(self.juengstes))
        self.assertTrue(Ereignis.objects.filter(pk=self.juengstes.pk).exists())


class LoeschenTest(Bestand):
    def test_absenden_loescht(self):
        antwort = self.client.post(self.adresse(self.juengstes))
        self.assertEqual(antwort.status_code, 302)
        self.assertFalse(Ereignis.objects.filter(pk=self.juengstes.pk).exists())

    def test_die_faelligkeit_rechnet_danach_ab_dem_vorherigen(self):
        from .faelligkeit import uebersicht

        self.client.post(self.adresse(self.juengstes))
        eintrag = uebersicht(heute=dt.date(2026, 3, 20))[0]
        self.assertEqual(eintrag.letzte_erledigung, dt.date(2026, 1, 16))
        self.assertEqual(eintrag.faellig_am, dt.date(2026, 2, 15))

    def test_anhaenge_wandern_in_den_papierkorb(self):
        from .anhaenge import anhaenge_speichern

        anhang = anhaenge_speichern(
            [echtes_bild()], self.bereich, self.benutzer, self.juengstes
        )[0]
        abgelegt = Path(anhang.datei.path)

        self.client.post(self.adresse(self.juengstes))

        self.assertFalse(Anhang.objects.filter(pk=anhang.pk).exists())
        self.assertFalse(abgelegt.exists())
        self.assertTrue(list((Path(self.ordner) / "geloescht").glob("*")))

    def test_die_aufgabe_bleibt_bestehen(self):
        self.client.post(self.adresse(self.juengstes))
        self.assertTrue(Aufgabe.objects.filter(pk=self.aufgabe.pk).exists())

    def test_fremdes_ereignis_ergibt_404(self):
        antwort = self.client.post(self.adresse(self.fremdes_ereignis))
        self.assertEqual(antwort.status_code, 404)
        self.assertTrue(Ereignis.objects.filter(pk=self.fremdes_ereignis.pk).exists())

    def test_fremde_rueckfrage_ergibt_404(self):
        antwort = self.client.get(self.adresse(self.fremdes_ereignis))
        self.assertEqual(antwort.status_code, 404)
        self.assertNotIn(b"Fremd", antwort.content)


class BereichsseiteTest(Bestand):
    def test_jede_historienzeile_hat_einen_loeschweg(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich.pk]))
        self.assertContains(antwort, self.adresse(self.juengstes))
        self.assertContains(antwort, self.adresse(self.aelter))


class EinzigeErledigungTest(Bestand):
    """Löscht man die einzige Erledigung, gibt es keine davorliegende — dann
    darf die Seite auch nicht behaupten, ab einer solchen zu rechnen."""

    def setUp(self):
        super().setUp()
        self.aelter.delete()  # jetzt ist self.juengstes die einzige

    def test_die_seite_spricht_nicht_von_einer_davorliegenden(self):
        antwort = self.client.get(self.adresse(self.juengstes))
        self.assertNotContains(antwort, "davorliegenden")

    def test_die_seite_sagt_dass_die_aufgabe_dann_offensteht(self):
        antwort = self.client.get(self.adresse(self.juengstes))
        self.assertContains(antwort, "noch nie erledigt")

    def test_bei_mehreren_bleibt_die_bisherige_aussage(self):
        Ereignis.objects.create(
            bereich=self.bereich, aufgabe=self.aufgabe, datum=dt.date(2026, 1, 16)
        )
        antwort = self.client.get(self.adresse(self.juengstes))
        self.assertContains(antwort, "davorliegenden")
