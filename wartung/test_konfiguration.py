"""Tests der Datenbankkonfiguration.

Anlass ist ein Fehler aus der ersten Inbetriebnahme: Die Zugangsdaten wurden im
Stack zu einer URL zusammengesetzt. Ein Passwort mit ":" und "/" zerreißt die
aber -- Python las einen Teil des Passworts als Portnummer, und beide Container
kamen nicht hoch.

Zugangsdaten gehören deshalb in eigene Variablen. Eine URL bleibt möglich, aber
sie ist nicht mehr der Weg, den der Betrieb geht.
"""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings

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


class ErlaubteHostsTest(SimpleTestCase):
    """Die Gesundheitsprüfung des Containers ruft die Anwendung über die
    eigene Loopback-Adresse auf. Fehlt die in ALLOWED_HOSTS, antwortet Django
    mit 400, der Container gilt als krank und wird endlos neu gestartet.
    """

    def test_eigene_adresse_ist_immer_erlaubt(self):
        from wartungsbuch.settings import erlaubte_hosts

        hosts = erlaubte_hosts({"DJANGO_ALLOWED_HOSTS": "wartung.example.org"})
        self.assertIn("wartung.example.org", hosts)
        self.assertIn("127.0.0.1", hosts)
        self.assertIn("localhost", hosts)

    def test_ohne_angabe_bleibt_nur_die_eigene_adresse(self):
        from wartungsbuch.settings import erlaubte_hosts

        self.assertEqual(sorted(erlaubte_hosts({})), ["127.0.0.1", "localhost"])

    def test_keine_doppelten_eintraege(self):
        from wartungsbuch.settings import erlaubte_hosts

        hosts = erlaubte_hosts({"DJANGO_ALLOWED_HOSTS": "localhost, wartung.example.org"})
        self.assertEqual(len(hosts), len(set(hosts)))


class LebenszeichenOhneUmleitungTest(TestCase):
    """Auch mit ALLOWED_HOSTS nützt die Prüfung nichts, wenn die Anwendung
    den Aufruf auf HTTPS umleitet: Die Prüfung erwartet 200, bekäme aber 301.
    """

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_gesund_wird_nicht_umgeleitet(self):
        self.assertEqual(self.client.get("/gesund").status_code, 200)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_andere_seiten_werden_weiterhin_umgeleitet(self):
        self.assertEqual(self.client.get("/anmelden/").status_code, 301)


class KalendermaskierungTest(SimpleTestCase):
    """Das Semikolon war mit einer ungültigen Escape-Folge geschrieben --
    inhaltlich richtig, aber Python warnt bei jedem Import."""

    def test_semikolon_wird_maskiert(self):
        from wartung.kalender import _maskieren

        self.assertEqual(_maskieren("Wartung; dringend"), "Wartung\; dringend")

    def test_komma_und_backslash_ebenso(self):
        from wartung.kalender import _maskieren

        self.assertEqual(_maskieren("a,b"), "a\\,b")
        self.assertEqual(_maskieren("a\\b"), "a\\\\b")


class MedienordnerPruefungTest(SimpleTestCase):
    """Ein nicht beschreibbarer Medienordner soll sich beim Start melden.

    Sonst merkt man es erst beim ersten Foto, und zwar als Server Error 500 --
    eine Antwort, aus der niemand die Ursache erraten kann.
    """

    def pruefen(self, ordner):
        from wartung.checks import medienordner_beschreibbar

        with self.settings(MEDIA_ROOT=str(ordner)):
            return medienordner_beschreibbar(None)

    def test_beschreibbarer_ordner_ist_still(self):
        import tempfile

        with tempfile.TemporaryDirectory() as ordner:
            self.assertEqual(self.pruefen(ordner), [])

    def test_nicht_beschreibbarer_ordner_wird_gemeldet(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as eltern:
            ordner = os.path.join(eltern, "gesperrt")
            os.mkdir(ordner, 0o500)
            try:
                meldungen = self.pruefen(ordner)
            finally:
                os.chmod(ordner, 0o700)
        self.assertEqual(len(meldungen), 1)
        self.assertIn("chown", meldungen[0].hint)

    def test_die_meldung_nennt_den_pfad(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as eltern:
            ordner = os.path.join(eltern, "gesperrt")
            os.mkdir(ordner, 0o500)
            try:
                meldungen = self.pruefen(ordner)
            finally:
                os.chmod(ordner, 0o700)
        self.assertIn("gesperrt", meldungen[0].msg)

    def test_fehlender_ordner_wird_angelegt(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as eltern:
            ordner = os.path.join(eltern, "gibtsnochnicht")
            self.assertEqual(self.pruefen(ordner), [])
            self.assertTrue(os.path.isdir(ordner))
