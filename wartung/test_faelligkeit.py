"""Tests der Faelligkeitsberechnung (SPEC 5, SPEC 6).

Der Kern der Anwendung: Ein Fehler hier bleibt still -- die Wochenmail meldet
dann einfach das Falsche, ohne dass irgendetwas abstuerzt. Deshalb erst die
Tests, dann der Code.

"heute" wird ueberall hineingereicht statt aus der Systemzeit gelesen. Das
haelt die Tests ohne Zusatzbibliothek reproduzierbar.
"""

import datetime as dt
import itertools

from django.core.exceptions import ValidationError
from django.test import TestCase

from .faelligkeit import Status, bewerten, monate_addieren, naechste_faelligkeit, uebersicht
from .models import (
    Aufgabe,
    Bereich,
    BereichsTyp,
    Einheit,
    Ereignis,
    Modus,
    Objekt,
    ObjektTyp,
    Taetigkeit,
)


_zaehler = itertools.count(1)


def datum(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


class MonateAddierenTest(TestCase):
    """Monatsarithmetik ohne Zusatzbibliothek."""

    def test_addiert_innerhalb_des_jahres(self):
        self.assertEqual(monate_addieren(datum("2026-03-12"), 3), datum("2026-06-12"))

    def test_ueberschreitet_den_jahreswechsel(self):
        self.assertEqual(monate_addieren(datum("2026-11-30"), 3), datum("2027-02-28"))

    def test_kappt_auf_das_monatsende(self):
        self.assertEqual(monate_addieren(datum("2026-01-31"), 1), datum("2026-02-28"))

    def test_beruecksichtigt_das_schaltjahr(self):
        self.assertEqual(monate_addieren(datum("2028-01-31"), 1), datum("2028-02-29"))

    def test_addiert_zwoelf_monate_zum_gleichen_tag(self):
        self.assertEqual(monate_addieren(datum("2026-03-12"), 12), datum("2027-03-12"))


class RelativeFaelligkeitTest(TestCase):
    """Modus "relativ zur letzten Erledigung" (SPEC 5)."""

    def setUp(self):
        self.aufgabe = _aufgabe(30, Einheit.TAGE)

    def test_dreissig_tage_nach_der_erledigung(self):
        self.assertEqual(
            naechste_faelligkeit(self.aufgabe, datum("2026-03-12"), heute=datum("2026-03-20")),
            datum("2026-04-11"),
        )

    def test_verspaetete_erledigung_verschiebt_die_naechste(self):
        """Die Uhr startet neu, wenn die Arbeit getan ist -- nicht, wenn sie
        geplant war. Ein Filter haelt 30 Tage ab Einbau."""
        puenktlich = naechste_faelligkeit(self.aufgabe, datum("2026-03-01"), heute=datum("2026-03-01"))
        verspaetet = naechste_faelligkeit(self.aufgabe, datum("2026-03-06"), heute=datum("2026-03-06"))
        self.assertEqual((verspaetet - puenktlich).days, 5)

    def test_intervall_in_monaten(self):
        aufgabe = _aufgabe(12, Einheit.MONATE)
        self.assertEqual(
            naechste_faelligkeit(aufgabe, datum("2026-01-31"), heute=datum("2026-02-01")),
            datum("2027-01-31"),
        )

    def test_intervall_in_jahren(self):
        aufgabe = _aufgabe(10, Einheit.JAHRE)
        self.assertEqual(
            naechste_faelligkeit(aufgabe, datum("2019-06-20"), heute=datum("2026-01-01")),
            datum("2029-06-20"),
        )

    def test_ohne_erledigung_ist_sofort_faellig(self):
        self.assertEqual(
            naechste_faelligkeit(self.aufgabe, None, heute=datum("2026-03-20")),
            datum("2026-03-20"),
        )


class KalenderFaelligkeitTest(TestCase):
    """Modus "fester Kalenderrhythmus" (SPEC 5)."""

    def setUp(self):
        self.jaehrlich_im_september = _aufgabe(
            1, Einheit.JAHRE, modus=Modus.KALENDER, kalender_monat=9
        )

    def test_termin_im_folgejahr_nach_puenktlicher_erledigung(self):
        self.assertEqual(
            naechste_faelligkeit(
                self.jaehrlich_im_september, datum("2026-09-15"), heute=datum("2026-09-16")
            ),
            datum("2027-09-01"),
        )

    def test_verspaetete_erledigung_verschiebt_den_termin_nicht(self):
        """Der Sinn des Kalendermodus: kein Wegdriften vom Termin."""
        self.assertEqual(
            naechste_faelligkeit(
                self.jaehrlich_im_september, datum("2026-11-20"), heute=datum("2026-11-21")
            ),
            datum("2027-09-01"),
        )

    def test_erledigung_lange_vor_dem_termin_ueberspringt_ihn_nicht(self):
        """Im Februar gewartet heisst nicht, dass der September ausfaellt."""
        self.assertEqual(
            naechste_faelligkeit(
                self.jaehrlich_im_september, datum("2026-02-10"), heute=datum("2026-03-01")
            ),
            datum("2026-09-01"),
        )

    def test_mehrjaehriger_rhythmus(self):
        streichen = _aufgabe(10, Einheit.JAHRE, modus=Modus.KALENDER, kalender_monat=5)
        self.assertEqual(
            naechste_faelligkeit(streichen, datum("2019-06-20"), heute=datum("2026-01-01")),
            datum("2029-05-01"),
        )

    def test_beruecksichtigt_den_kalendertag(self):
        aufgabe = _aufgabe(
            1, Einheit.JAHRE, modus=Modus.KALENDER, kalender_monat=11, kalender_tag=15
        )
        self.assertEqual(
            naechste_faelligkeit(aufgabe, datum("2026-11-20"), heute=datum("2026-12-01")),
            datum("2027-11-15"),
        )

    def test_ohne_erledigung_ist_der_letzte_vergangene_termin_faellig(self):
        self.assertEqual(
            naechste_faelligkeit(self.jaehrlich_im_september, None, heute=datum("2026-11-05")),
            datum("2026-09-01"),
        )

    def test_kalendermodus_verlangt_jahre_als_einheit(self):
        """Ein Monatsintervall und ein fester Monat widersprechen einander."""
        aufgabe = _aufgabe(6, Einheit.MONATE, modus=Modus.KALENDER, kalender_monat=5, speichern=False)
        with self.assertRaises(ValidationError):
            aufgabe.full_clean()


class BewertenTest(TestCase):
    """Aus dem Faelligkeitsdatum wird ein Status (SPEC 6)."""

    def setUp(self):
        self.aufgabe = _aufgabe(30, Einheit.TAGE)

    def test_nie_erledigt_ist_ein_eigener_status(self):
        """"Ueberfaellig seit 1970" waere eine Luege."""
        ergebnis = bewerten(self.aufgabe, None, heute=datum("2026-03-20"))
        self.assertEqual(ergebnis.status, Status.NIE_ERLEDIGT)
        self.assertEqual(ergebnis.tage_ueberfaellig, 0)

    def test_ueberfaellig_zaehlt_die_tage(self):
        ergebnis = bewerten(self.aufgabe, datum("2026-01-01"), heute=datum("2026-02-05"))
        self.assertEqual(ergebnis.status, Status.UEBERFAELLIG)
        self.assertEqual(ergebnis.faellig_am, datum("2026-01-31"))
        self.assertEqual(ergebnis.tage_ueberfaellig, 5)

    def test_heute_faellig(self):
        ergebnis = bewerten(self.aufgabe, datum("2026-01-01"), heute=datum("2026-01-31"))
        self.assertEqual(ergebnis.status, Status.FAELLIG)
        self.assertEqual(ergebnis.tage_ueberfaellig, 0)

    def test_innerhalb_des_vorschaufensters(self):
        ergebnis = bewerten(
            self.aufgabe, datum("2026-01-01"), heute=datum("2026-01-20"), vorschau_tage=14
        )
        self.assertEqual(ergebnis.status, Status.BALD)

    def test_ausserhalb_des_vorschaufensters(self):
        ergebnis = bewerten(
            self.aufgabe, datum("2026-01-01"), heute=datum("2026-01-05"), vorschau_tage=14
        )
        self.assertEqual(ergebnis.status, Status.OFFEN)


class RuhezeitTest(TestCase):
    """Die Ruhezeit unterdrueckt Meldungen, nicht die Berechnung (SPEC 6)."""

    def setUp(self):
        self.aufgabe = _aufgabe(30, Einheit.TAGE, aktiv_ab_monat=4, aktiv_bis_monat=10)
        Ereignis.objects.create(
            bereich=self.aufgabe.bereich, aufgabe=self.aufgabe, datum=datum("2026-10-01")
        )

    def test_im_winter_ueberfaellig_aber_nicht_meldbar(self):
        ergebnis = bewerten(self.aufgabe, datum("2026-10-01"), heute=datum("2027-01-15"))
        self.assertEqual(ergebnis.status, Status.UEBERFAELLIG)
        self.assertFalse(ergebnis.wird_gemeldet)

    def test_zum_saisonstart_wieder_meldbar(self):
        ergebnis = bewerten(self.aufgabe, datum("2026-10-01"), heute=datum("2027-04-02"))
        self.assertEqual(ergebnis.status, Status.UEBERFAELLIG)
        self.assertTrue(ergebnis.wird_gemeldet)

    def test_uebersicht_kann_auf_meldbare_beschraenken(self):
        im_winter = uebersicht(heute=datum("2027-01-15"), nur_meldbare=True)
        self.assertEqual(im_winter, [])
        zum_saisonstart = uebersicht(heute=datum("2027-04-02"), nur_meldbare=True)
        self.assertEqual(len(zum_saisonstart), 1)


class UebersichtTest(TestCase):
    def setUp(self):
        self.aufgabe = _aufgabe(30, Einheit.TAGE)

    def test_nimmt_das_juengste_ereignis_nicht_das_zuletzt_erfasste(self):
        """Nachgetragene Ereignisse korrigieren rueckwirkend (SPEC 4)."""
        Ereignis.objects.create(
            bereich=self.aufgabe.bereich, aufgabe=self.aufgabe, datum=datum("2026-03-01")
        )
        Ereignis.objects.create(
            bereich=self.aufgabe.bereich, aufgabe=self.aufgabe, datum=datum("2026-01-05")
        )
        eintrag = uebersicht(heute=datum("2026-03-10"))[0]
        self.assertEqual(eintrag.letzte_erledigung, datum("2026-03-01"))
        self.assertEqual(eintrag.faellig_am, datum("2026-03-31"))

    def test_ereignis_ohne_aufgabe_beeinflusst_die_faelligkeit_nicht(self):
        Ereignis.objects.create(
            bereich=self.aufgabe.bereich, beschreibung="Bad renoviert", datum=datum("2026-03-01")
        )
        eintrag = uebersicht(heute=datum("2026-03-10"))[0]
        self.assertIsNone(eintrag.letzte_erledigung)
        self.assertEqual(eintrag.status, Status.NIE_ERLEDIGT)

    def test_stillgelegte_aufgaben_erscheinen_nicht(self):
        self.aufgabe.aktiv = False
        self.aufgabe.save()
        self.assertEqual(uebersicht(heute=datum("2026-03-10")), [])

    def test_sortiert_das_draengendste_nach_oben(self):
        zweite = _aufgabe(30, Einheit.TAGE, schluessel="zweite")
        Ereignis.objects.create(
            bereich=self.aufgabe.bereich, aufgabe=self.aufgabe, datum=datum("2026-03-01")
        )
        Ereignis.objects.create(bereich=zweite.bereich, aufgabe=zweite, datum=datum("2026-01-01"))
        eintraege = uebersicht(heute=datum("2026-04-15"))
        self.assertEqual([e.aufgabe.pk for e in eintraege], [zweite.pk, self.aufgabe.pk])

    def test_stellt_nicht_pro_aufgabe_eine_abfrage(self):
        for nummer in range(5):
            _aufgabe(30, Einheit.TAGE, schluessel=f"weitere-{nummer}")
        with self.assertNumQueries(1):
            uebersicht(heute=datum("2026-03-10"))


def _aufgabe(
    wert,
    einheit,
    *,
    modus=Modus.RELATIV,
    kalender_monat=None,
    kalender_tag=None,
    aktiv_ab_monat=None,
    aktiv_bis_monat=None,
    schluessel=None,
    objektname="Haupthaus",
    speichern=True,
):
    """Baut eine Aufgabe samt Objekt und Bereich.

    Ohne ausdruecklichen Schluessel bekommt jede Aufgabe eine eigene
    Taetigkeit -- pro Bereich ist jede Taetigkeit nur einmal erlaubt.
    """
    schluessel = schluessel or f"taetigkeit-{next(_zaehler)}"
    objekt_typ, _ = ObjektTyp.objects.get_or_create(schluessel="haus", defaults={"name_de": "Haus"})
    bereichs_typ, _ = BereichsTyp.objects.get_or_create(
        schluessel="waermepumpe", defaults={"name_de": "Wärmepumpe"}
    )
    taetigkeit, _ = Taetigkeit.objects.get_or_create(
        schluessel=schluessel, defaults={"name_de": schluessel}
    )
    objekt, _ = Objekt.objects.get_or_create(
        name=objektname,
        defaults={
            "typ": objekt_typ,
            "aktiv_ab_monat": aktiv_ab_monat,
            "aktiv_bis_monat": aktiv_bis_monat,
        },
    )
    bereich, _ = Bereich.objects.get_or_create(objekt=objekt, typ=bereichs_typ, bezeichnung_de="")
    aufgabe = Aufgabe(
        bereich=bereich,
        taetigkeit=taetigkeit,
        intervall_wert=wert,
        intervall_einheit=einheit,
        modus=modus,
        kalender_monat=kalender_monat,
        kalender_tag=kalender_tag,
    )
    if speichern:
        aufgabe.save()
    return aufgabe


class KatalogDatenTest(TestCase):
    """Die Katalogvorgaben muessen die Regeln erfuellen, die fuer Aufgaben gelten.

    Sonst erzeugt der Vorlagenkatalog in Schritt 3 Aufgaben, die die Datenbank
    zurueckweist.
    """

    def test_kalendervorgaben_zaehlen_in_jahren_und_nennen_einen_monat(self):
        from .katalogdaten import TAETIGKEITEN

        for eintrag in TAETIGKEITEN:
            if eintrag.get("modus") != Modus.KALENDER:
                continue
            with self.subTest(schluessel=eintrag["schluessel"]):
                self.assertEqual(eintrag["einheit"], Einheit.JAHRE)
                self.assertIn(eintrag.get("monat"), range(1, 13))

    def test_jede_vorgabe_hat_wert_und_einheit(self):
        from .katalogdaten import TAETIGKEITEN

        for eintrag in TAETIGKEITEN:
            with self.subTest(schluessel=eintrag["schluessel"]):
                self.assertGreaterEqual(eintrag["wert"], 1)
                self.assertIn(eintrag["einheit"], [w for w, _ in Einheit.choices])


class UebersichtSichtbarkeitTest(TestCase):
    """Die Übersicht liefert nur, was der Betrachter sehen darf (SPEC 2)."""

    def setUp(self):
        from .models import Benutzer

        self.eigene = _aufgabe(30, Einheit.TAGE, schluessel="eigene")
        self.fremde = _aufgabe(30, Einheit.TAGE, schluessel="fremde", objektname="Sommerhaus")
        self.betreuer = Benutzer.objects.create_user("hilfe@example.org")
        self.betreuer.zugewiesene_objekte.add(self.eigene.bereich.objekt)

    def test_ohne_angabe_unveraendert_alles(self):
        self.assertEqual(len(uebersicht(heute=datum("2026-03-10"))), 2)

    def test_fuer_betreuer_nur_zugewiesenes(self):
        eintraege = uebersicht(heute=datum("2026-03-10"), fuer=self.betreuer)
        self.assertEqual([e.aufgabe.pk for e in eintraege], [self.eigene.pk])

    def test_fuer_unbeteiligten_nichts(self):
        from .models import Benutzer

        fremder = Benutzer.objects.create_user("fremd@example.org")
        self.assertEqual(uebersicht(heute=datum("2026-03-10"), fuer=fremder), [])

    def test_verwaltung_sieht_weiterhin_alles(self):
        from .models import Benutzer

        chef = Benutzer.objects.create_user("chef@example.org", is_staff=True)
        self.assertEqual(len(uebersicht(heute=datum("2026-03-10"), fuer=chef)), 2)

    def test_bleibt_bei_einer_abfrage(self):
        with self.assertNumQueries(1):
            uebersicht(heute=datum("2026-03-10"), fuer=self.betreuer)


class HorizontTest(TestCase):
    """Das Dashboard zeigt, was ansteht -- nicht, was 2031 ansteht.

    Überfälliges und noch nie Erledigtes bleibt immer sichtbar: Es ist ja
    gerade das, was drängt.
    """

    def setUp(self):
        self.bald = _aufgabe(30, Einheit.TAGE, schluessel="bald")
        Ereignis.objects.create(
            bereich=self.bald.bereich, aufgabe=self.bald, datum=datum("2026-03-01")
        )
        self.fern = _aufgabe(5, Einheit.JAHRE, schluessel="fern")
        Ereignis.objects.create(
            bereich=self.fern.bereich, aufgabe=self.fern, datum=datum("2026-03-01")
        )
        self.ueberfaellig = _aufgabe(30, Einheit.TAGE, schluessel="ueberfaellig")
        Ereignis.objects.create(
            bereich=self.ueberfaellig.bereich, aufgabe=self.ueberfaellig, datum=datum("2025-01-01")
        )
        self.nie = _aufgabe(30, Einheit.TAGE, schluessel="nie")

    def schluessel(self, **kwargs):
        return {
            e.aufgabe.taetigkeit.schluessel
            for e in uebersicht(heute=datum("2026-03-10"), **kwargs)
        }

    def test_ohne_horizont_unveraendert_alles(self):
        self.assertEqual(len(self.schluessel()), 4)

    def test_horizont_blendet_fernes_aus(self):
        self.assertNotIn("fern", self.schluessel(horizont_tage=30))

    def test_horizont_zeigt_was_bald_faellig_wird(self):
        self.assertIn("bald", self.schluessel(horizont_tage=30))

    def test_ueberfaelliges_bleibt_immer_sichtbar(self):
        self.assertIn("ueberfaellig", self.schluessel(horizont_tage=1))

    def test_nie_erledigtes_bleibt_immer_sichtbar(self):
        self.assertIn("nie", self.schluessel(horizont_tage=1))

    def test_kurzer_horizont_blendet_auch_bald_faelliges_aus(self):
        self.assertNotIn("bald", self.schluessel(horizont_tage=5))
