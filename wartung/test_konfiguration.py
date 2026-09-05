"""Tests der Datenbankkonfiguration.

Anlass ist ein Fehler aus der ersten Inbetriebnahme: Die Zugangsdaten wurden im
Stack zu einer URL zusammengesetzt. Ein Passwort mit ":" und "/" zerreißt die
aber -- Python las einen Teil des Passworts als Portnummer, und beide Container
kamen nicht hoch.

Zugangsdaten gehören deshalb in eigene Variablen. Eine URL bleibt möglich, aber
sie ist nicht mehr der Weg, den der Betrieb geht.
"""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from wartungsbuch.settings import datenbank_konfiguration

BOESES_PASSWORT = "Xy:0lMt/pw@rd?#&=+ "


class EinzelvariablenTest(SimpleTestCase):
    def test_baut_die_verbindung_aus_einzelwerten(self):
        ergebnis = datenbank_konfiguration(
            {
                "POSTGRES_HOST": "datenbank",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "wartungsbuch",
                "POSTGRES_USER": "wartung",
                "POSTGRES_PASSWORD": BOESES_PASSWORT,
            }
        )
        self.assertEqual(ergebnis["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(ergebnis["HOST"], "datenbank")
        self.assertEqual(ergebnis["PORT"], "5432")
        self.assertEqual(ergebnis["NAME"], "wartungsbuch")
        self.assertEqual(ergebnis["USER"], "wartung")
        self.assertEqual(ergebnis["PASSWORD"], BOESES_PASSWORT)

    def test_sonderzeichen_bleiben_unangetastet(self):
        """Kein Zeichen im Passwort darf die Konfiguration stören."""
        for passwort in ["a:b", "a/b", "a@b", "a?b", "a#b", "a b", "a%20b", "a\\b", 'a"b']:
            with self.subTest(passwort=passwort):
                ergebnis = datenbank_konfiguration(
                    {"POSTGRES_HOST": "datenbank", "POSTGRES_PASSWORD": passwort}
                )
                self.assertEqual(ergebnis["PASSWORD"], passwort)

    def test_einzelwerte_haben_vorrang_vor_der_url(self):
        ergebnis = datenbank_konfiguration(
            {
                "POSTGRES_HOST": "datenbank",
                "POSTGRES_PASSWORD": "geheim",
                "DATABASE_URL": "postgres://wer:was@woanders:5432/andere",
            }
        )
        self.assertEqual(ergebnis["HOST"], "datenbank")

    def test_port_hat_eine_sinnvolle_vorgabe(self):
        ergebnis = datenbank_konfiguration({"POSTGRES_HOST": "datenbank"})
        self.assertEqual(ergebnis["PORT"], "5432")


class UrlTest(SimpleTestCase):
    def test_url_wird_weiterhin_verstanden(self):
        ergebnis = datenbank_konfiguration(
            {"DATABASE_URL": "postgres://wartung:geheim@datenbank:5432/wartungsbuch"}
        )
        self.assertEqual(ergebnis["HOST"], "datenbank")
        self.assertEqual(ergebnis["PORT"], "5432")
        self.assertEqual(ergebnis["PASSWORD"], "geheim")

    def test_prozentkodiertes_passwort_wird_entschluesselt(self):
        ergebnis = datenbank_konfiguration(
            {"DATABASE_URL": "postgres://wartung:a%3Ab%2Fc@datenbank:5432/wartungsbuch"}
        )
        self.assertEqual(ergebnis["PASSWORD"], "a:b/c")

    def test_zerrissene_url_meldet_sich_verstaendlich(self):
        """Die Meldung muss sagen, was zu tun ist -- nicht nur, dass etwas
        nicht nach einer Zahl aussieht."""
        with self.assertRaises(ImproperlyConfigured) as fehler:
            datenbank_konfiguration({"DATABASE_URL": "postgres://w:Xy:0lMt/pw@datenbank:5432/db"})
        meldung = str(fehler.exception)
        self.assertIn("DATABASE_URL", meldung)
        self.assertIn("POSTGRES_HOST", meldung)

    def test_fremdes_schema_wird_abgelehnt(self):
        with self.assertRaises(ImproperlyConfigured):
            datenbank_konfiguration({"DATABASE_URL": "mysql://w:x@h:3306/db"})


class OhneAngabenTest(SimpleTestCase):
    def test_faellt_auf_sqlite_zurueck(self):
        ergebnis = datenbank_konfiguration({})
        self.assertEqual(ergebnis["ENGINE"], "django.db.backends.sqlite3")
