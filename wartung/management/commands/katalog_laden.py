"""Legt den Vorlagenkatalog an oder bringt ihn auf Stand.

    python manage.py katalog_laden

Der Befehl ist wiederholbar: Vorhandene Eintraege werden anhand ihres
Schluessels aktualisiert, nichts wird geloescht. Eigene Ergaenzungen im Admin
bleiben erhalten.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from wartung.katalogdaten import BEREICHS_TYPEN, OBJEKT_TYPEN, TAETIGKEITEN
from wartung.models import BereichsTyp, Modus, ObjektTyp, Taetigkeit


class Command(BaseCommand):
    help = "Laedt den dreisprachigen Vorlagenkatalog (idempotent)."

    @transaction.atomic
    def handle(self, *args, **optionen):
        for modell, daten, bezeichnung in [
            (ObjektTyp, OBJEKT_TYPEN, "Objekttypen"),
            (BereichsTyp, BEREICHS_TYPEN, "Bereichstypen"),
        ]:
            neu = 0
            for schluessel, de, en, sv, sortierung in daten:
                _, angelegt = modell.objects.update_or_create(
                    schluessel=schluessel,
                    defaults={
                        "name_de": de,
                        "name_en": en,
                        "name_sv": sv,
                        "sortierung": sortierung,
                    },
                )
                neu += angelegt
            self.stdout.write(f"{bezeichnung}: {len(daten)} gepflegt, davon {neu} neu")

        bereichs_typen = {b.schluessel: b for b in BereichsTyp.objects.all()}
        neu = 0
        for eintrag in TAETIGKEITEN:
            taetigkeit, angelegt = Taetigkeit.objects.update_or_create(
                schluessel=eintrag["schluessel"],
                defaults={
                    "name_de": eintrag["de"],
                    "name_en": eintrag["en"],
                    "name_sv": eintrag["sv"],
                    "hinweis_de": eintrag.get("hinweis_de", ""),
                    "hinweis_en": eintrag.get("hinweis_en", ""),
                    "hinweis_sv": eintrag.get("hinweis_sv", ""),
                    "standard_intervall_wert": eintrag.get("wert"),
                    "standard_intervall_einheit": eintrag.get("einheit", ""),
                    "standard_modus": eintrag.get("modus", Modus.RELATIV),
                    "standard_kalender_monat": eintrag.get("monat"),
                    "sortierung": eintrag.get("sortierung", 100),
                },
            )
            neu += angelegt
            fehlend = [s for s in eintrag["bereiche"] if s not in bereichs_typen]
            if fehlend:
                self.stderr.write(
                    self.style.WARNING(
                        f"{eintrag['schluessel']}: unbekannte Bereichstypen {fehlend}"
                    )
                )
            taetigkeit.bereichs_typen.set(
                [bereichs_typen[s] for s in eintrag["bereiche"] if s in bereichs_typen]
            )
        self.stdout.write(f"Taetigkeiten: {len(TAETIGKEITEN)} gepflegt, davon {neu} neu")
        self.stdout.write(self.style.SUCCESS("Katalog ist auf Stand."))
