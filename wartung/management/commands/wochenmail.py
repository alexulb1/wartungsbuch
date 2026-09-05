"""Verschickt die woechentliche Sammelmail (SPEC 6).

    python manage.py wochenmail

Eine Mail je aktivem Konto, in dessen Sprache, nach Objekt gruppiert -- damit
sich Fahrten buendeln lassen. Steht nichts an, geht keine Mail raus: Stille ist
besser als eine Mail ohne Inhalt.
"""

import datetime as dt

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from wartung.faelligkeit import VORSCHAU_TAGE, Status, uebersicht
from wartung.mail import adresse, senden
from wartung.models import Benutzer, Zugangsmarke, Zweck


class Command(BaseCommand):
    help = "Verschickt die wöchentliche Sammelmail an alle aktiven Konten."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stichtag", help="Abweichender Stichtag im Format JJJJ-MM-TT (für Proben)."
        )
        parser.add_argument(
            "--probe", action="store_true", help="Nur anzeigen, nichts verschicken."
        )

    def handle(self, *args, **optionen):
        heute = (
            dt.date.fromisoformat(optionen["stichtag"])
            if optionen.get("stichtag")
            else timezone.localdate()
        )

        eintraege = [
            eintrag
            for eintrag in uebersicht(heute=heute, nur_meldbare=True)
            if eintrag.status != Status.OFFEN
        ]
        if not eintraege:
            self.stdout.write("Nichts fällig – keine Mail verschickt.")
            return

        empfaenger = Benutzer.objects.filter(is_active=True)
        verschickt = 0
        for benutzer in empfaenger:
            gruppen = self._gruppieren(eintraege, benutzer, heute, trocken=optionen["probe"])
            if optionen["probe"]:
                self.stdout.write(f"{benutzer.email}: {len(eintraege)} Einträge")
                continue
            senden(
                benutzer,
                "wartung/mail/wochenmail_betreff.txt",
                "wartung/mail/wochenmail.txt",
                {
                    "benutzer": benutzer,
                    "gruppen": gruppen,
                    "heute": heute,
                    "vorschau_tage": VORSCHAU_TAGE,
                    "anzahl": len(eintraege),
                },
            )
            verschickt += 1
        self.stdout.write(
            self.style.SUCCESS(f"{verschickt} Mail(s) mit {len(eintraege)} Eintrag/Einträgen.")
        )

    def _gruppieren(self, eintraege, benutzer, heute, trocken=False):
        """Nach Objekt gruppieren und je Aufgabe eine eigene Abhakmarke ausgeben.

        Die Marken sind an den Empfaenger gebunden: Damit steht in der Historie
        spaeter, wer abgehakt hat, auch ohne Anmeldung.
        """
        reihenfolge, gruppen = [], {}
        for eintrag in eintraege:
            objekt = eintrag.aufgabe.bereich.objekt
            if objekt.pk not in gruppen:
                reihenfolge.append(objekt.pk)
                gruppen[objekt.pk] = {
                    "objekt": objekt,
                    # Faengt gerade die Saison an, ist das die Ankunftsliste:
                    # alles, was sich ueber die Ruhezeit angesammelt hat.
                    "saisonstart": objekt.hat_ruhezeit and heute.month == objekt.aktiv_ab_monat,
                    "zeilen": [],
                }
            link = ""
            if not trocken:
                _, roh = Zugangsmarke.objects.anlegen(
                    Zweck.ERLEDIGUNG, benutzer, aufgabe=eintrag.aufgabe
                )
                link = adresse(reverse("wartung:erledigt_mit_marke", args=[roh]))
            gruppen[objekt.pk]["zeilen"].append({"eintrag": eintrag, "link": link})
        return [gruppen[pk] for pk in reihenfolge]
