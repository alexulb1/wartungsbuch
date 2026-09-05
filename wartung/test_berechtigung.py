"""Wirkung der Berechtigung an den Ansichten (SPEC 2)."""

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


class ZweiObjekte(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")

        self.haus = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.sommerhaus = Objekt.objects.create(name="Sommerhaus", typ=objekt_typ)

        self.bereich_haus = Bereich.objects.create(objekt=self.haus, typ=bereichs_typ)
        self.bereich_sommer = Bereich.objects.create(objekt=self.sommerhaus, typ=bereichs_typ)

        self.aufgabe_haus = Aufgabe.objects.create(
            bereich=self.bereich_haus,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        self.aufgabe_sommer = Aufgabe.objects.create(
            bereich=self.bereich_sommer,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )
        Ereignis.objects.create(
            bereich=self.bereich_sommer,
            beschreibung="Sommerhaus renoviert",
            datum=dt.date(2026, 1, 1),
        )

        self.betreuer = Benutzer.objects.create_user("hilfe@example.org", name="Hilfe")
        self.betreuer.zugewiesene_objekte.add(self.haus)
        self.client.force_login(self.betreuer)


class DashboardBerechtigungTest(ZweiObjekte):
    def test_zeigt_nur_zugewiesenes(self):
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "Haupthaus")
        self.assertNotContains(antwort, "Sommerhaus")

    def test_ohne_zuweisung_leer(self):
        self.betreuer.zugewiesene_objekte.clear()
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertNotContains(antwort, "Haupthaus")
        self.assertNotContains(antwort, "Sommerhaus")


class DetailseitenTest(ZweiObjekte):
    def test_fremder_bereich_ergibt_404(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich_sommer.pk]))
        self.assertEqual(antwort.status_code, 404)

    def test_eigener_bereich_ist_erreichbar(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich_haus.pk]))
        self.assertEqual(antwort.status_code, 200)

    def test_fremde_aufgabe_laesst_sich_nicht_abhaken(self):
        antwort = self.client.post(
            reverse("wartung:erledigen", args=[self.aufgabe_sommer.pk]), {"datum": "2026-03-12"}
        )
        self.assertEqual(antwort.status_code, 404)
        self.assertFalse(Ereignis.objects.filter(aufgabe=self.aufgabe_sommer).exists())

    def test_fremder_bereich_nimmt_kein_ereignis_an(self):
        antwort = self.client.post(
            reverse("wartung:ereignis_neu", args=[self.bereich_sommer.pk]),
            {"datum": "2026-03-12", "beschreibung": "Eingeschmuggelt"},
        )
        self.assertEqual(antwort.status_code, 404)
        self.assertFalse(Ereignis.objects.filter(beschreibung="Eingeschmuggelt").exists())

    def test_fremder_bereich_nimmt_keine_katalogaufgaben(self):
        antwort = self.client.get(
            reverse("wartung:aufgaben_ergaenzen", args=[self.bereich_sommer.pk])
        )
        self.assertEqual(antwort.status_code, 404)


class AusgabenTest(ZweiObjekte):
    def test_csv_enthaelt_nur_zugewiesenes(self):
        inhalt = self.client.get(reverse("wartung:export_csv")).content.decode("utf-8-sig")
        self.assertNotIn("Sommerhaus", inhalt)

    def test_kalender_enthaelt_nur_zugewiesenes(self):
        antwort = self.client.get(
            reverse("wartung:kalender", args=[self.betreuer.kalender_schluessel])
        )
        text = antwort.content.decode()
        self.assertIn("Haupthaus", text)
        self.assertNotIn("Sommerhaus", text)


class VerwaltungTest(ZweiObjekte):
    def setUp(self):
        super().setUp()
        self.chef = Benutzer.objects.create_user("chef@example.org", is_staff=True)
        self.client.force_login(self.chef)

    def test_verwaltung_sieht_beides(self):
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "Haupthaus")
        self.assertContains(antwort, "Sommerhaus")

    def test_verwaltung_erreicht_jeden_bereich(self):
        antwort = self.client.get(reverse("wartung:bereich", args=[self.bereich_sommer.pk]))
        self.assertEqual(antwort.status_code, 200)


class WochenmailBerechtigungTest(ZweiObjekte):
    def wochenmail(self, stichtag="2026-03-10"):
        from io import StringIO

        from django.core.management import call_command

        call_command("wochenmail", stichtag=stichtag, stdout=StringIO())

    def test_empfaenger_sieht_nur_seine_objekte(self):
        from django.core import mail

        self.wochenmail()
        an_betreuer = [n for n in mail.outbox if "hilfe@example.org" in n.to][0]
        self.assertIn("Haupthaus", an_betreuer.body)
        self.assertNotIn("Sommerhaus", an_betreuer.body)

    def test_ohne_zuweisung_keine_mail(self):
        from django.core import mail

        self.betreuer.zugewiesene_objekte.clear()
        self.wochenmail()
        self.assertEqual([n for n in mail.outbox if "hilfe@example.org" in n.to], [])

    def test_verwaltung_bekommt_alles(self):
        from django.core import mail

        Benutzer.objects.create_user("chef@example.org", is_staff=True)
        self.wochenmail()
        an_chef = [n for n in mail.outbox if "chef@example.org" in n.to][0]
        self.assertIn("Haupthaus", an_chef.body)
        self.assertIn("Sommerhaus", an_chef.body)


class MarkeNachEntzugTest(ZweiObjekte):
    """Entzogen heißt entzogen -- auch für Links, die schon draußen sind."""

    def setUp(self):
        super().setUp()
        from .models import Zugangsmarke, Zweck

        _, self.roh = Zugangsmarke.objects.anlegen(
            Zweck.ERLEDIGUNG, self.betreuer, aufgabe=self.aufgabe_haus
        )

    def test_marke_wirkt_solange_die_zuweisung_besteht(self):
        antwort = self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertEqual(antwort.status_code, 200)

    def test_entzogene_zuweisung_entwertet_die_marke_sofort(self):
        self.betreuer.zugewiesene_objekte.clear()
        antwort = self.client.get(reverse("wartung:erledigt_mit_marke", args=[self.roh]))
        self.assertEqual(antwort.status_code, 404)

    def test_entzogene_zuweisung_verhindert_auch_das_absenden(self):
        self.betreuer.zugewiesene_objekte.clear()
        antwort = self.client.post(
            reverse("wartung:erledigt_mit_marke", args=[self.roh]), {"datum": "2026-03-12"}
        )
        self.assertEqual(antwort.status_code, 404)
        self.assertFalse(Ereignis.objects.filter(aufgabe=self.aufgabe_haus).exists())

    def test_bestehende_ereignisse_bleiben_nach_entzug(self):
        """Die Historie ist die Wahrheit und wird nicht umgeschrieben."""
        Ereignis.objects.create(
            bereich=self.bereich_haus,
            aufgabe=self.aufgabe_haus,
            datum=dt.date(2026, 2, 1),
            erfasst_von=self.betreuer,
        )
        self.betreuer.zugewiesene_objekte.clear()
        eintrag = Ereignis.objects.get(aufgabe=self.aufgabe_haus)
        self.assertEqual(eintrag.erfasst_von, self.betreuer)


class WaechterTest(ZweiObjekte):
    """Geht alle Adressen mit Objektbezug durch und prüft, dass ein fremdes
    Objekt nirgends durchkommt.

    Zweck ist ausdrücklich, künftige Lücken zu verhindern: Eine neue Ansicht,
    die den Filter vergisst, lässt diesen Test umfallen, ohne dass jemand daran
    denken muss. Kommt eine Route mit Objektbezug hinzu, gehört sie hier
    eingetragen -- der Test besteht darauf.
    """

    #: Routenname -> Feld dieses Tests, dessen fremdes Objekt eingesetzt wird.
    ROUTEN_MIT_OBJEKTBEZUG = {
        "bereich": "bereich_sommer",
        "aufgaben_ergaenzen": "bereich_sommer",
        "ereignis_neu": "bereich_sommer",
        "erledigen": "aufgabe_sommer",
    }

    #: Routen ohne Objektbezug -- sie brauchen diese Prüfung nicht.
    OHNE_OBJEKTBEZUG = {
        "dashboard",
        "profil",
        "anmelden",
        "anmelden_mit_marke",
        "abmelden",
        "erledigt_mit_marke",
        "kalender",
        "export_csv",
        "lebenszeichen",
    }

    def test_alle_routen_sind_eingeordnet(self):
        """Neue Routen müssen bewusst zugeordnet werden."""
        from wartung import urls

        bekannt = set(self.ROUTEN_MIT_OBJEKTBEZUG) | self.OHNE_OBJEKTBEZUG
        vorhanden = {muster.name for muster in urls.urlpatterns}
        self.assertEqual(
            vorhanden - bekannt,
            set(),
            "Neue Route gefunden: bitte in ROUTEN_MIT_OBJEKTBEZUG oder "
            "OHNE_OBJEKTBEZUG eintragen und, falls nötig, absichern.",
        )

    def test_fremdes_objekt_kommt_nirgends_durch(self):
        for route, feld in self.ROUTEN_MIT_OBJEKTBEZUG.items():
            fremdes = getattr(self, feld)
            adresse = reverse(f"wartung:{route}", args=[fremdes.pk])
            with self.subTest(route=route, methode="GET"):
                antwort = self.client.get(adresse)
                self.assertEqual(antwort.status_code, 404)
                self.assertNotIn(b"Sommerhaus", antwort.content)
            with self.subTest(route=route, methode="POST"):
                antwort = self.client.post(adresse, {"datum": "2026-03-12"})
                self.assertEqual(antwort.status_code, 404)

    def test_ohne_zuweisung_kommt_auch_eigenes_nicht_durch(self):
        self.betreuer.zugewiesene_objekte.clear()
        for route, feld in self.ROUTEN_MIT_OBJEKTBEZUG.items():
            eigenes = getattr(self, feld.replace("sommer", "haus"))
            with self.subTest(route=route):
                antwort = self.client.get(reverse(f"wartung:{route}", args=[eigenes.pk]))
                self.assertEqual(antwort.status_code, 404)
