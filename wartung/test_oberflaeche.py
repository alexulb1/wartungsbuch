"""Tests der Oberflaeche (SPEC 2, SPEC 3, SPEC 7).

Geprueft wird Verhalten, nicht Gestaltung: Wer was sehen darf, was ein Klick
bewirkt, und in welcher Sprache die Seite erscheint.
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
    Modus,
    Objekt,
    ObjektTyp,
    Taetigkeit,
)


def datum(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


class Grunddaten(TestCase):
    """Gemeinsamer Bestand: ein Haus mit Waermepumpe und Nordfassade."""

    def setUp(self):
        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.client.force_login(self.benutzer)

        haus_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus", name_en="House", name_sv="Hus")
        self.wp_typ = BereichsTyp.objects.create(
            schluessel="waermepumpe", name_de="Wärmepumpe", name_en="Heat pump", name_sv="Värmepump"
        )
        self.fassade_typ = BereichsTyp.objects.create(
            schluessel="fassade", name_de="Fassade", name_en="Facade", name_sv="Fasad"
        )
        self.filter = Taetigkeit.objects.create(
            schluessel="luftfilter",
            name_de="Luftfilter wechseln",
            name_en="Replace air filter",
            name_sv="Byta luftfilter",
            standard_intervall_wert=30,
            standard_intervall_einheit=Einheit.TAGE,
        )
        self.filter.bereichs_typen.add(self.wp_typ)
        self.streichen = Taetigkeit.objects.create(
            schluessel="streichen", name_de="Streichen", name_en="Paint", name_sv="Måla"
        )
        self.streichen.bereichs_typen.add(self.fassade_typ)

        self.haus = Objekt.objects.create(name="Haupthaus", typ=haus_typ)
        # Seit Einführung der Berechtigungen sieht man nur Zugewiesenes (SPEC 2).
        self.benutzer.zugewiesene_objekte.add(self.haus)
        self.wp = Bereich.objects.create(objekt=self.haus, typ=self.wp_typ)
        self.nord = Bereich.objects.create(objekt=self.haus, typ=self.fassade_typ, bezeichnung="Nord")
        self.aufgabe = Aufgabe.objects.create(
            bereich=self.wp,
            taetigkeit=self.filter,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )


class ZugangTest(Grunddaten):
    def test_ohne_anmeldung_keine_daten(self):
        self.client.logout()
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertEqual(antwort.status_code, 302)
        self.assertNotIn(b"Haupthaus", antwort.content)

    def test_angemeldet_erreichbar(self):
        self.assertEqual(self.client.get(reverse("wartung:dashboard")).status_code, 200)


class DashboardTest(Grunddaten):
    def test_zeigt_ueberfaellige_aufgabe(self):
        Ereignis.objects.create(bereich=self.wp, aufgabe=self.aufgabe, datum=datum("2026-01-01"))
        antwort = self.client.get(reverse("wartung:dashboard"), {"stichtag": "2026-03-01"})
        self.assertContains(antwort, "Luftfilter wechseln")
        self.assertContains(antwort, "Haupthaus")

    def test_nennt_den_status_im_klartext(self):
        Ereignis.objects.create(bereich=self.wp, aufgabe=self.aufgabe, datum=datum("2026-01-01"))
        antwort = self.client.get(reverse("wartung:dashboard"), {"stichtag": "2026-03-01"})
        self.assertContains(antwort, "überfällig")

    def test_nie_erledigte_aufgabe_wird_so_benannt(self):
        antwort = self.client.get(reverse("wartung:dashboard"), {"stichtag": "2026-03-01"})
        self.assertContains(antwort, "noch nie erledigt")

    def test_ruhendes_objekt_bleibt_sichtbar_ist_aber_gekennzeichnet(self):
        """Die Ruhezeit unterdrueckt Meldungen, nicht die Anzeige (SPEC 6)."""
        sommer_typ = ObjektTyp.objects.create(schluessel="sommerhaus", name_de="Sommerhaus")
        sommerhaus = Objekt.objects.create(
            name="Sommerhaus", typ=sommer_typ, aktiv_ab_monat=4, aktiv_bis_monat=10
        )
        self.benutzer.zugewiesene_objekte.add(sommerhaus)
        bereich = Bereich.objects.create(objekt=sommerhaus, typ=self.wp_typ)
        aufgabe = Aufgabe.objects.create(
            bereich=bereich, taetigkeit=self.filter, intervall_wert=30, intervall_einheit=Einheit.TAGE
        )
        Ereignis.objects.create(bereich=bereich, aufgabe=aufgabe, datum=datum("2026-10-01"))

        antwort = self.client.get(reverse("wartung:dashboard"), {"stichtag": "2027-01-15"})
        self.assertContains(antwort, "Sommerhaus")
        self.assertContains(antwort, "ruht")


class BereichTest(Grunddaten):
    def test_historie_zeigt_juengstes_zuerst(self):
        Ereignis.objects.create(bereich=self.nord, beschreibung="Gestrichen", datum=datum("2019-06-20"))
        Ereignis.objects.create(bereich=self.nord, beschreibung="Gereinigt", datum=datum("2024-05-04"))
        antwort = self.client.get(reverse("wartung:bereich", args=[self.nord.pk]))
        inhalt = antwort.content.decode()
        self.assertLess(inhalt.index("Gereinigt"), inhalt.index("Gestrichen"))

    def test_beantwortet_wann_die_nordseite_zuletzt_dran_war(self):
        Ereignis.objects.create(bereich=self.nord, beschreibung="Gestrichen", datum=datum("2019-06-20"))
        antwort = self.client.get(reverse("wartung:bereich", args=[self.nord.pk]))
        self.assertContains(antwort, "Fassade Nord")
        self.assertContains(antwort, "20.06.2019")

    def test_zeigt_ereignisse_fremder_bereiche_nicht(self):
        Ereignis.objects.create(bereich=self.wp, aufgabe=self.aufgabe, datum=datum("2026-01-01"))
        antwort = self.client.get(reverse("wartung:bereich", args=[self.nord.pk]))
        self.assertNotContains(antwort, "Luftfilter wechseln")


class ErledigenTest(Grunddaten):
    def test_abhaken_legt_ereignis_an(self):
        antwort = self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]),
            {"datum": "2026-03-12", "kosten": "45.50", "ausgefuehrt_von": "Fa. Müller", "notiz": "RAL 7016"},
        )
        self.assertEqual(antwort.status_code, 302)
        ereignis = Ereignis.objects.get()
        self.assertEqual(ereignis.datum, datum("2026-03-12"))
        self.assertEqual(ereignis.aufgabe, self.aufgabe)
        self.assertEqual(ereignis.bereich, self.wp)
        self.assertEqual(ereignis.notiz, "RAL 7016")

    def test_haelt_fest_wer_abgehakt_hat(self):
        self.client.post(reverse("wartung:erledigen", args=[self.aufgabe.pk]), {"datum": "2026-03-12"})
        self.assertEqual(Ereignis.objects.get().erfasst_von, self.benutzer)

    def test_datum_ist_frei_waehlbar_und_wirkt_rueckwirkend(self):
        """Sonntags eintragen, was freitags geschah (SPEC 4)."""
        self.client.post(reverse("wartung:erledigen", args=[self.aufgabe.pk]), {"datum": "2026-03-06"})
        from .faelligkeit import uebersicht

        eintrag = uebersicht(heute=datum("2026-03-08"))[0]
        self.assertEqual(eintrag.faellig_am, datum("2026-04-05"))

    def test_formular_belegt_das_datum_mit_heute_vor(self):
        antwort = self.client.get(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]), {"stichtag": "2026-03-12"}
        )
        self.assertContains(antwort, "2026-03-12")


class VorlagenTest(Grunddaten):
    def test_schlaegt_nur_passende_taetigkeiten_vor(self):
        antwort = self.client.get(reverse("wartung:aufgaben_ergaenzen", args=[self.nord.pk]))
        self.assertContains(antwort, "Streichen")
        self.assertNotContains(antwort, "Luftfilter wechseln")

    def test_uebernimmt_vorlage_samt_intervall(self):
        self.client.post(
            reverse("wartung:aufgaben_ergaenzen", args=[self.nord.pk]),
            {"taetigkeit": [str(self.streichen.pk)]},
        )
        aufgabe = Aufgabe.objects.get(bereich=self.nord)
        self.assertEqual(aufgabe.taetigkeit, self.streichen)

    def test_bereits_angelegte_taetigkeit_wird_nicht_erneut_vorgeschlagen(self):
        antwort = self.client.get(reverse("wartung:aufgaben_ergaenzen", args=[self.wp.pk]))
        self.assertNotContains(antwort, "Luftfilter wechseln")


class FreiesEreignisTest(Grunddaten):
    def test_einmaliger_vorgang_ohne_aufgabe(self):
        antwort = self.client.post(
            reverse("wartung:ereignis_neu", args=[self.nord.pk]),
            {"datum": "2019-06-20", "beschreibung": "Bad renoviert"},
        )
        self.assertEqual(antwort.status_code, 302)
        ereignis = Ereignis.objects.get()
        self.assertIsNone(ereignis.aufgabe)
        self.assertEqual(ereignis.beschreibung, "Bad renoviert")

    def test_ohne_beschreibung_und_ohne_taetigkeit_abgelehnt(self):
        antwort = self.client.post(
            reverse("wartung:ereignis_neu", args=[self.nord.pk]), {"datum": "2019-06-20"}
        )
        self.assertEqual(antwort.status_code, 200)  # Formular mit Fehler
        self.assertFalse(Ereignis.objects.exists())


class SpracheTest(Grunddaten):
    def test_katalogbegriffe_erscheinen_in_der_profilsprache(self):
        self.benutzer.sprache = "sv"
        self.benutzer.save()
        antwort = self.client.get(reverse("wartung:bereich", args=[self.wp.pk]))
        self.assertContains(antwort, "Värmepump")
        self.assertNotContains(antwort, "Wärmepumpe")

    def test_englisch(self):
        self.benutzer.sprache = "en"
        self.benutzer.save()
        antwort = self.client.get(reverse("wartung:bereich", args=[self.wp.pk]))
        self.assertContains(antwort, "Heat pump")

    def test_profil_erlaubt_das_umstellen(self):
        antwort = self.client.post(reverse("wartung:profil"), {"sprache": "sv", "name": "Alex"})
        self.assertEqual(antwort.status_code, 302)
        self.benutzer.refresh_from_db()
        self.assertEqual(self.benutzer.sprache, "sv")


class SicherheitTest(Grunddaten):
    def test_seiten_tragen_eine_content_security_policy(self):
        antwort = self.client.get(reverse("wartung:dashboard"))
        richtlinie = antwort.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", richtlinie)
        self.assertIn("frame-ancestors 'none'", richtlinie)

    def test_fremde_objekte_gibt_es_nicht_zu_erraten(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[9999]))
        self.assertEqual(antwort.status_code, 404)


class UebersetzteOberflaecheTest(Grunddaten):
    """Nicht nur Katalogbegriffe, auch die Oberflaechentexte selbst (SPEC 3)."""

    def test_schwedisch(self):
        self.benutzer.sprache = "sv"
        self.benutzer.save()
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "Vad som är aktuellt")
        self.assertNotContains(antwort, "Was ansteht")

    def test_englisch(self):
        self.benutzer.sprache = "en"
        self.benutzer.save()
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "What is due")

    def test_status_erscheint_uebersetzt(self):
        self.benutzer.sprache = "sv"
        self.benutzer.save()
        antwort = self.client.get(reverse("wartung:dashboard"), {"stichtag": "2026-03-01"})
        self.assertContains(antwort, "aldrig utförd")

    def test_deutsch_bleibt_deutsch(self):
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "Was ansteht")


class VorbelegungTest(Grunddaten):
    """"ausgeführt von" mit dem Namen vorbelegen, der das Formular aufruft.

    Im Regelfall macht man die Arbeit selbst; dann ist das Feld ohne einen
    Tastendruck richtig. Es bleibt überschreibbar -- steht dort eine Firma,
    gehört die Firma hinein.
    """

    def test_abhakformular_traegt_den_eigenen_namen(self):
        antwort = self.client.get(reverse("wartung:erledigen", args=[self.aufgabe.pk]))
        self.assertContains(antwort, 'value="Alex"')

    def test_formular_fuer_einmaliges_ebenso(self):
        antwort = self.client.get(reverse("wartung:ereignis_neu", args=[self.nord.pk]))
        self.assertContains(antwort, 'value="Alex"')

    def test_ohne_hinterlegten_namen_bleibt_das_feld_leer(self):
        """Ein Adressfragment wäre als "ausgeführt von" unsinnig."""
        self.benutzer.name = ""
        self.benutzer.save()
        antwort = self.client.get(reverse("wartung:erledigen", args=[self.aufgabe.pk]))
        self.assertNotContains(antwort, "ich@example.org")

    def test_vorbelegung_laesst_sich_ueberschreiben(self):
        self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]),
            {"datum": "2026-03-12", "ausgefuehrt_von": "Fa. Berg"},
        )
        self.assertEqual(Ereignis.objects.get().ausgefuehrt_von, "Fa. Berg")

    def test_vorbelegung_laesst_sich_leeren(self):
        self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe.pk]),
            {"datum": "2026-03-12", "ausgefuehrt_von": ""},
        )
        self.assertEqual(Ereignis.objects.get().ausgefuehrt_von, "")
