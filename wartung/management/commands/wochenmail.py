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

from django.conf import settings

from wartung.faelligkeit import VORSCHAU_TAGE, Status, uebersicht
from wartung.mail import adresse, senden
from wartung.models import Benutzer, Mailversand, Zugangsmarke, Zweck
from wartung.versandplan import soll_senden, wochenkennung


class Command(BaseCommand):
    help = "Verschickt die wöchentliche Sammelmail an alle aktiven Konten."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stichtag", help="Abweichender Stichtag im Format JJJJ-MM-TT (für Proben)."
        )
        parser.add_argument(
            "--probe", action="store_true", help="Nur anzeigen, nichts verschicken."
        )
        parser.add_argument(
            "--geplant",
            action="store_true",
            help="Nur verschicken, wenn der Versandtag erreicht und diese Woche noch "
            "nichts rausging. Für den stündlich laufenden Zeitplaner.",
        )
        parser.add_argument("--jetzt", help="Abweichender Zeitpunkt (für Proben).")
        parser.add_argument(
            "--wochentag", type=int, help="0 = Montag … 6 = Sonntag. Sonst aus der Konfiguration."
        )
        parser.add_argument("--stunde", type=int, help="Frühestens ab dieser Stunde.")

    def handle(self, *args, **optionen):
        jetzt = (
            dt.datetime.fromisoformat(optionen["jetzt"]).replace(tzinfo=timezone.get_current_timezone())
            if optionen.get("jetzt")
            else timezone.localtime()
        )

        if optionen["geplant"]:
            diese_woche = wochenkennung(jetzt)
            schon_gelaufen = Mailversand.objects.filter(woche=diese_woche).exists()
            if not soll_senden(
                jetzt,
                diese_woche if schon_gelaufen else None,
                optionen["wochentag"]
                if optionen["wochentag"] is not None
                else settings.WOCHENMAIL_WOCHENTAG,
                optionen["stunde"] if optionen["stunde"] is not None else settings.WOCHENMAIL_STUNDE,
            ):
                self.stdout.write("Noch nicht dran – nichts verschickt.")
                return
            optionen.setdefault("stichtag", None)

        heute = (
            dt.date.fromisoformat(optionen["stichtag"])
            if optionen.get("stichtag")
            else jetzt.date()
        )

        # Je Empfänger neu berechnet: Jeder sieht nur seine Objekte (SPEC 2).
        empfaenger = Benutzer.objects.filter(is_active=True)
        verschickt = 0
        gesamt = 0
        for benutzer in empfaenger:
            eintraege = [
                eintrag
                for eintrag in uebersicht(heute=heute, nur_meldbare=True, fuer=benutzer)
                if eintrag.status != Status.OFFEN
            ]
            if not eintraege:
                continue
            # Die Listen der Empfänger überschneiden sich; als Kennzahl für das
            # Versandprotokoll dient die längste verschickte Liste.
            gesamt = max(gesamt, len(eintraege))
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

        if optionen["geplant"] and not optionen["probe"]:
            # Der Eintrag ist zugleich die Sperre gegen einen zweiten Versand
            # in derselben Woche.
            Mailversand.objects.update_or_create(
                woche=wochenkennung(jetzt),
                defaults={"anzahl_mails": verschickt, "anzahl_eintraege": gesamt},
            )

        self.stdout.write(
            self.style.SUCCESS(f"{verschickt} Mail(s) mit {gesamt} Eintrag/Einträgen.")
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
