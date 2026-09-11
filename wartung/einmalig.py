"""Einmal gespeichert, auch wenn ein Formular zweimal ankommt.

Ein Doppelklick, ein hängendes Netz, ein erneutes Absenden durch den Browser:
Dasselbe Formular trifft zweimal ein. Jedes angezeigte Formular trägt deshalb
eine Einmal-Kennung, und die Datenbank lässt jede Kennung nur einmal zu -- das
hält auch dann, wenn sich zwei Anfragen überholen.

Doppelt ist nur, was mit derselben Kennung, vom selben Urheber und mit
demselben Inhalt kommt. Wer mit "Zurück" das alte Formular vor sich hat und
bewusst etwas anderes einträgt, bekommt einen weiteren Eintrag.
"""

from django.db import IntegrityError, transaction

from .models import Ereignis

#: Woran man erkennt, dass es derselbe Vorgang ist.
INHALT = (
    "bereich_id",
    "aufgabe_id",
    "taetigkeit_id",
    "beschreibung",
    "datum",
    "kosten",
    "ausgefuehrt_von",
    "notiz",
    "erfasst_von_id",
)


def mit_kennung(kennung):
    return Ereignis.objects.filter(absendekennung=kennung).first()


def _derselbe(vorhanden, entwurf) -> bool:
    return all(getattr(vorhanden, feld) == getattr(entwurf, feld) for feld in INHALT)


def einmal_speichern(formular):
    """Speichert ein gültiges Ereignisformular höchstens einmal.

    Gibt (ereignis, neu) zurück. Bei einer Wiederholung ist es der Eintrag von
    vorhin und neu ist False -- Anhänge dürfen dann nicht noch einmal abgelegt
    werden.
    """
    kennung = formular.cleaned_data.get("absendekennung")
    entwurf = formular.instance
    if kennung is None:
        # Eine Seite, die vor dem Update geöffnet wurde: speichern wie bisher.
        return formular.save(), True

    vorhanden = mit_kennung(kennung)
    if vorhanden is None:
        entwurf.absendekennung = kennung
        try:
            with transaction.atomic():
                return formular.save(), True
        except IntegrityError:
            # Eine gleichzeitige Anfrage mit derselben Kennung war schneller.
            entwurf.absendekennung = None
            vorhanden = mit_kennung(kennung)

    if vorhanden is not None and _derselbe(vorhanden, entwurf):
        return vorhanden, False

    # Kennung schon vergeben, aber anderer Inhalt oder anderer Urheber: ein
    # bewusst weiterer Eintrag, nur ohne Schutz vor seiner eigenen Wiederholung.
    entwurf.absendekennung = None
    return formular.save(), True
