"""Tests fuer Datensicherung und Zeitplaner (SPEC 9, SPEC 10.4)."""

import datetime as dt
import json
from io import StringIO
from pathlib import Path

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import (
    Aufgabe,
    Benutzer,
    Bereich,
    BereichsTyp,
    Einheit,
    Ereignis,
    Mailversand,
    Objekt,
    ObjektTyp,
    Taetigkeit,
)


def bestand():
    benutzer = Benutzer.objects.create_user("ich@example.org")
    haus_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
    wp_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
    taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")
    objekt = Objekt.objects.create(name="Haupthaus", typ=haus_typ)
    bereich = Bereich.objects.create(objekt=objekt, typ=wp_typ)
    aufgabe = Aufgabe.objects.create(
        bereich=bereich, taetigkeit=taetigkeit, intervall_wert=30, intervall_einheit=Einheit.TAGE
    )
    Ereignis.objects.create(bereich=bereich, aufgabe=aufgabe, datum=dt.date(2026, 1, 1))
    # Seit Einführung der Berechtigungen sieht man nur Zugewiesenes (SPEC 2).
    benutzer.zugewiesene_objekte.add(objekt)
    return aufgabe


class SicherungTest(TestCase):
    def setUp(self):
        bestand()

    def sichern(self, verzeichnis, **optionen):
        call_command("sicherung", verzeichnis=str(verzeichnis), stdout=StringIO(), **optionen)

    def test_schreibt_eine_lesbare_datei(self, ):
        import tempfile

        with tempfile.TemporaryDirectory() as ordner:
            self.sichern(ordner)
            dateien = list(Path(ordner).glob("*.json"))
            self.assertEqual(len(dateien), 1)
            daten = json.loads(dateien[0].read_text())
            modelle = {eintrag["model"] for eintrag in daten}
            self.assertIn("wartung.ereignis", modelle)
            self.assertIn("wartung.objekt", modelle)

    def test_enthaelt_keine_zugangsmarken(self):
        """Marken gehoeren nicht in eine Sicherung -- sie sind fluechtig und
        haetten dort nur Angriffsflaeche."""
        import tempfile

        with tempfile.TemporaryDirectory() as ordner:
            self.sichern(ordner)
            daten = json.loads(next(Path(ordner).glob("*.json")).read_text())
            self.assertNotIn("wartung.zugangsmarke", {e["model"] for e in daten})

    def test_taeglich_schreibt_nur_einmal(self):
        import tempfile

        with tempfile.TemporaryDirectory() as ordner:
            self.sichern(ordner, taeglich=True)
            self.sichern(ordner, taeglich=True)
            self.assertEqual(len(list(Path(ordner).glob("*.json"))), 1)

    def test_raeumt_alte_sicherungen_ab(self):
        import tempfile

        with tempfile.TemporaryDirectory() as ordner:
            for tag in range(1, 12):
                (Path(ordner) / f"wartungsbuch-2026-01-{tag:02d}.json").write_text("[]")
            self.sichern(ordner, behalten=5)
            uebrig = sorted(p.name for p in Path(ordner).glob("*.json"))
            self.assertEqual(len(uebrig), 5)
            # Die juengsten bleiben.
            self.assertIn(uebrig[-1], (f"wartungsbuch-2026-01-11.json", uebrig[-1]))


class PlanerTest(TestCase):
    def setUp(self):
        bestand()

    def test_ein_durchlauf_verschickt_am_versandtag(self):
        call_command("planer", einmal=True, jetzt="2027-01-11T07:00", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Mailversand.objects.exists())

    def test_ein_durchlauf_schweigt_ausserhalb(self):
        call_command("planer", einmal=True, jetzt="2027-01-11T05:00", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_ein_fehler_beendet_den_planer_nicht(self):
        """Ueber zehn Jahre wird irgendwann etwas schiefgehen -- ein
        Zeitplaner, der daran stirbt, bleibt fuer immer stehen."""
        from unittest import mock

        ausgabe = StringIO()
        with mock.patch(
            "wartung.management.commands.planer.Command.wochenmail",
            side_effect=RuntimeError("Mailserver nicht erreichbar"),
        ):
            call_command("planer", einmal=True, jetzt="2027-01-11T07:00", stdout=ausgabe, stderr=ausgabe)
        self.assertIn("Mailserver nicht erreichbar", ausgabe.getvalue())


class LebenszeichenTest(TestCase):
    """Der Container muss sagen können, ob er arbeitsfähig ist (SPEC 9)."""

    def test_ohne_anmeldung_erreichbar(self):
        from django.urls import reverse

        antwort = self.client.get(reverse("wartung:lebenszeichen"))
        self.assertEqual(antwort.status_code, 200)

    def test_bestaetigt_die_datenbankverbindung(self):
        from django.urls import reverse

        antwort = self.client.get(reverse("wartung:lebenszeichen"))
        self.assertEqual(antwort.json()["datenbank"], "erreichbar")

    def test_verraet_nichts_ueber_den_bestand(self):
        """Ein offener Endpunkt gibt keine Auskunft über Objekte oder Konten."""
        bestand()
        from django.urls import reverse

        inhalt = self.client.get(reverse("wartung:lebenszeichen")).content.decode()
        self.assertNotIn("Haupthaus", inhalt)
        self.assertNotIn("example.org", inhalt)


class AnhaengeAufraeumenTest(TestCase):
    """Gelöschtes bleibt 30 Tage zurückholbar, danach ist es Ballast."""

    def setUp(self):
        import shutil
        import tempfile

        self.ordner = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.ueberschreiben = override_settings(MEDIA_ROOT=self.ordner)
        self.ueberschreiben.enable()
        self.addCleanup(self.ueberschreiben.disable)

        self.korb = Path(self.ordner) / "geloescht"
        self.korb.mkdir()

    def datei(self, name, alter_tage):
        import os
        import time

        pfad = self.korb / name
        pfad.write_bytes(b"x")
        zeitpunkt = time.time() - alter_tage * 86400
        os.utime(pfad, (zeitpunkt, zeitpunkt))
        return pfad

    def test_alte_dateien_verschwinden(self):
        alt = self.datei("alt.jpg", 40)
        call_command("anhaenge_aufraeumen", stdout=StringIO())
        self.assertFalse(alt.exists())

    def test_junge_dateien_bleiben(self):
        jung = self.datei("jung.jpg", 3)
        call_command("anhaenge_aufraeumen", stdout=StringIO())
        self.assertTrue(jung.exists())

    def test_ohne_papierkorb_kein_fehler(self):
        import shutil

        shutil.rmtree(self.korb)
        call_command("anhaenge_aufraeumen", stdout=StringIO())


class SicherungNenntAnhaengeTest(TestCase):
    def test_die_zahl_der_anhaenge_steht_in_der_ausgabe(self):
        import tempfile

        with tempfile.TemporaryDirectory() as ordner:
            ausgabe = StringIO()
            call_command("sicherung", verzeichnis=ordner, stdout=ausgabe)
            self.assertIn("Anhänge", ausgabe.getvalue())
