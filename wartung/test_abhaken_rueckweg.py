"""Nach dem Abhaken zurück dorthin, wo man angefangen hat.

Der Arbeitsvorrat ist die Übersicht: Dort sucht man sich eine Aufgabe aus,
hakt sie ab -- und will danach die naechste aussuchen, nicht auf der
Bereichsseite stehen. Wer dagegen auf der Bereichsseite abhakt, bleibt dort.

Das Ziel kommt aus der Adresse und ist deshalb streng geprueft: Nur die
ausdruecklich genannten Seiten, nur bekannte Abfrageparameter. Ein frei
waehlbares Ziel waere eine offene Weiterleitung.
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
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")

        self.objekt = Objekt.objects.create(name="Singenberg", typ=objekt_typ)
        self.bereich = Bereich.objects.create(objekt=self.objekt, typ=bereichs_typ)
        self.aufgabe = Aufgabe.objects.create(
            bereich=self.bereich,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )

        self.benutzer = Benutzer.objects.create_user("ich@example.org", name="Alex")
        self.benutzer.zugewiesene_objekte.add(self.objekt)
        self.client.force_login(self.benutzer)

        self.uebersicht = reverse("wartung:dashboard")
        self.bereichsseite = reverse("wartung:bereich", args=[self.bereich.pk])
        self.abhaken = reverse("wartung:erledigen", args=[self.aufgabe.pk])

    def daten(self, **aenderung):
        daten = {"datum": "2026-07-18", "kosten": "", "ausgefuehrt_von": "Alex", "notiz": ""}
        daten.update(aenderung)
        return daten


class ArbeitsvorratTest(Bestand):
    def test_der_abhaklink_merkt_sich_die_uebersicht(self):
        antwort = self.client.get(self.uebersicht)
        self.assertContains(antwort, f"{self.abhaken}?zurueck=")

    def test_nach_dem_abhaken_zurueck_in_den_arbeitsvorrat(self):
        antwort = self.client.post(self.abhaken, self.daten(zurueck=self.uebersicht))
        self.assertRedirects(antwort, self.uebersicht, fetch_redirect_response=False)
        self.assertEqual(Ereignis.objects.count(), 1)

    def test_der_ausschnitt_der_uebersicht_bleibt_erhalten(self):
        """Wer alles eingeblendet hatte, steht danach nicht wieder vor 30 Tagen."""
        ziel = self.uebersicht + "?horizont=alle"
        antwort = self.client.post(self.abhaken, self.daten(zurueck=ziel))
        self.assertRedirects(antwort, ziel, fetch_redirect_response=False)

    def test_das_formular_traegt_das_ziel_mit(self):
        antwort = self.client.get(self.abhaken, {"zurueck": self.uebersicht})
        self.assertContains(antwort, f'name="zurueck" value="{self.uebersicht}"')
        self.assertContains(antwort, f'class="abbruch" href="{self.uebersicht}"')


class BereichsseiteTest(Bestand):
    def test_ohne_angabe_bleibt_es_bei_der_bereichsseite(self):
        antwort = self.client.post(self.abhaken, self.daten())
        self.assertRedirects(antwort, self.bereichsseite, fetch_redirect_response=False)

    def test_von_der_bereichsseite_zurueck_zur_bereichsseite(self):
        antwort = self.client.post(self.abhaken, self.daten(zurueck=self.bereichsseite))
        self.assertRedirects(antwort, self.bereichsseite, fetch_redirect_response=False)


class FremdeZieleTest(Bestand):
    def test_werden_nicht_angesteuert(self):
        for ziel in (
            "https://boese.example/",
            "//boese.example" + self.uebersicht,
            "https://boese.example" + self.uebersicht,
            "/\\boese.example/",
            reverse("wartung:profil"),
            reverse("wartung:nachweis", args=[self.objekt.pk]),
        ):
            with self.subTest(ziel=ziel):
                Ereignis.objects.all().delete()
                antwort = self.client.post(self.abhaken, self.daten(zurueck=ziel))
                self.assertRedirects(
                    antwort, self.bereichsseite, fetch_redirect_response=False
                )

    def test_unbekannte_parameter_fallen_weg(self):
        ziel = self.uebersicht + "?horizont=alle&weiter=https://boese.example&stichtag=unfug"
        antwort = self.client.post(self.abhaken, self.daten(zurueck=ziel))
        self.assertRedirects(
            antwort, self.uebersicht + "?horizont=alle", fetch_redirect_response=False
        )
