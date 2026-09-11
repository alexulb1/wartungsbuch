"""Doppeltes Absenden legt keinen zweiten Eintrag an.

Ein Doppelklick auf "Eintragen", ein hängendes Netz, ein erneutes Absenden
durch den Browser -- jedes Mal kommt dasselbe Formular zweimal an. Der Browser
sperrt den Knopf nach dem ersten Klick; darauf verlässt sich der Server nicht,
denn ohne JavaScript oder bei Wiederholung durch den Browser greift das nicht.
Jedes angezeigte Formular trägt deshalb eine Einmal-Kennung.

Doppelt ist nur, was mit derselben Kennung *und* demselben Inhalt kommt: Wer
mit "Zurück" das alte Formular wieder vor sich hat und bewusst einen weiteren
Eintrag erfasst, soll nicht stillschweigend verschluckt werden.
"""

import datetime as dt
import re
import uuid
from unittest import mock

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from . import einmalig
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
    Zugangsmarke,
    Zweck,
)


class Bestand(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="fassade", name_de="Fassade")
        taetigkeit = Taetigkeit.objects.create(schluessel="reinigen", name_de="Fassade reinigen")

        self.objekt = Objekt.objects.create(name="Singenberg", typ=objekt_typ)
        self.bereich = Bereich.objects.create(objekt=self.objekt, typ=bereichs_typ)
        self.aufgabe = Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=taetigkeit,
            intervall_wert=1,
            intervall_einheit=Einheit.JAHRE,
        )

        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.benutzer.zugewiesene_objekte.add(self.objekt)
        self.client.force_login(self.benutzer)

    def kennung_aus(self, adresse):
        """Die Kennung, die das angezeigte Formular mitbringt."""
        inhalt = self.client.get(adresse).content.decode()
        treffer = re.search(r'name="absendekennung" value="([0-9a-f-]{36})"', inhalt)
        self.assertIsNotNone(treffer, "Das Formular trägt keine Absendekennung.")
        return treffer.group(1)


class ErledigenTest(Bestand):
    def adresse(self):
        return reverse("wartung:erledigen", args=[self.aufgabe.pk])

    def daten(self, **aenderung):
        daten = {
            "datum": "2026-07-18",
            "kosten": "",
            "ausgefuehrt_von": "Alex",
            "notiz": "",
            "absendekennung": self.kennung_aus(self.adresse()),
        }
        daten.update(aenderung)
        return daten

    def test_das_formular_traegt_eine_kennung(self):
        self.kennung_aus(self.adresse())

    def test_jedes_angezeigte_formular_bekommt_eine_eigene(self):
        self.assertNotEqual(self.kennung_aus(self.adresse()), self.kennung_aus(self.adresse()))

    def test_doppelt_abgeschickt_ergibt_einen_eintrag(self):
        daten = self.daten()
        erste = self.client.post(self.adresse(), daten)
        zweite = self.client.post(self.adresse(), daten)

        self.assertEqual(Ereignis.objects.count(), 1)
        # Die Wiederholung sieht aus wie ein Erfolg -- es war ja einer.
        bereichsseite = reverse("wartung:bereich", args=[self.bereich.pk])
        self.assertRedirects(erste, bereichsseite, fetch_redirect_response=False)
        self.assertRedirects(zweite, bereichsseite, fetch_redirect_response=False)

    def test_gleichzeitig_abgeschickt_ergibt_einen_eintrag(self):
        """Zwei Anfragen, die sich überholen: Beide finden noch nichts vor.
        Die Datenbank lässt die Kennung trotzdem nur einmal zu."""
        daten = self.daten()
        self.client.post(self.adresse(), daten)

        echt = einmalig.mit_kennung
        aufrufe = []

        def zu_spaet_gesehen(kennung):
            aufrufe.append(kennung)
            return None if len(aufrufe) == 1 else echt(kennung)

        with mock.patch.object(einmalig, "mit_kennung", side_effect=zu_spaet_gesehen):
            antwort = self.client.post(self.adresse(), daten)

        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(Ereignis.objects.count(), 1)

    def test_mit_anderem_inhalt_ist_es_ein_neuer_eintrag(self):
        """Zurück, Datum geändert, nochmal abgeschickt: Das ist Absicht."""
        daten = self.daten()
        self.client.post(self.adresse(), daten)
        self.client.post(self.adresse(), dict(daten, datum="2026-07-19"))
        self.assertEqual(Ereignis.objects.count(), 2)

    def test_ohne_kennung_wird_gespeichert_wie_bisher(self):
        """Eine Seite, die noch vor dem Update geöffnet wurde, hat keine."""
        daten = self.daten()
        del daten["absendekennung"]
        antwort = self.client.post(self.adresse(), daten)
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(Ereignis.objects.count(), 1)

    def test_die_kennung_eines_anderen_blockiert_nichts(self):
        """Eine eingeschleuste fremde Kennung verhindert den eigenen Eintrag nicht."""
        andere = Benutzer.objects.create_user("du@example.org", name="Kim")
        andere.zugewiesene_objekte.add(self.objekt)
        kennung = uuid.uuid4()
        Ereignis.objects.create(
            aufgabe=self.aufgabe,
            datum=dt.date(2026, 7, 18),
            ausgefuehrt_von="Alex",
            erfasst_von=andere,
            absendekennung=kennung,
        )

        antwort = self.client.post(self.adresse(), self.daten(absendekennung=str(kennung)))

        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(Ereignis.objects.filter(erfasst_von=self.benutzer).count(), 1)

    def test_anhaenge_werden_nicht_doppelt_abgelegt(self):
        import shutil
        import tempfile
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from PIL import Image

        from .models import Anhang

        ordner = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, ordner, True)
        puffer = BytesIO()
        Image.new("RGB", (80, 60)).save(puffer, format="JPEG")
        daten = self.daten()

        with override_settings(MEDIA_ROOT=ordner):
            for _ in range(2):
                bild = SimpleUploadedFile("fassade.jpg", puffer.getvalue(), content_type="image/jpeg")
                self.client.post(self.adresse(), dict(daten, anhaenge=bild))

        self.assertEqual(Ereignis.objects.count(), 1)
        self.assertEqual(Anhang.objects.count(), 1)

    def test_eine_verfaelschte_kennung_speichert_nichts(self):
        antwort = self.client.post(self.adresse(), self.daten(absendekennung="unfug"))
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Ereignis.objects.count(), 0)


class EreignisNeuTest(Bestand):
    def adresse(self):
        return reverse("wartung:ereignis_neu", args=[self.bereich.pk])

    def daten(self, **aenderung):
        daten = {
            "datum": "2026-04-01",
            "taetigkeit": "",
            "beschreibung": "Fassade Ost gereinigt",
            "kosten": "",
            "ausgefuehrt_von": "Alex",
            "notiz": "",
            "absendekennung": self.kennung_aus(self.adresse()),
        }
        daten.update(aenderung)
        return daten

    def test_doppelt_abgeschickt_ergibt_einen_eintrag(self):
        daten = self.daten()
        self.client.post(self.adresse(), daten)
        self.client.post(self.adresse(), daten)
        self.assertEqual(Ereignis.objects.count(), 1)

    def test_mit_anderem_inhalt_ist_es_ein_neuer_eintrag(self):
        daten = self.daten()
        self.client.post(self.adresse(), daten)
        self.client.post(self.adresse(), dict(daten, beschreibung="Fassade West gereinigt"))
        self.assertEqual(Ereignis.objects.count(), 2)


class MailLinkTest(Bestand):
    def test_doppelt_abgeschickt_ergibt_einen_eintrag(self):
        self.client.logout()
        _, roh = Zugangsmarke.objects.anlegen(Zweck.ERLEDIGUNG, self.benutzer, aufgabe=self.aufgabe)
        adresse = reverse("wartung:erledigt_mit_marke", args=[roh])
        daten = {
            "datum": "2026-07-18",
            "ausgefuehrt_von": "Alex",
            "absendekennung": self.kennung_aus(adresse),
        }
        self.client.post(adresse, daten)
        self.client.post(adresse, daten)
        self.assertEqual(Ereignis.objects.count(), 1)


class BrowserSperreTest(Bestand):
    """Die erste Schicht: Der Knopf nimmt nach dem ersten Klick nichts mehr an."""

    def test_die_seiten_laden_die_sperre(self):
        antwort = self.client.get(reverse("wartung:ereignis_neu", args=[self.bereich.pk]))
        self.assertContains(antwort, "wartung/absenden.js")

    def test_die_datei_gibt_es(self):
        self.assertIsNotNone(finders.find("wartung/absenden.js"))
