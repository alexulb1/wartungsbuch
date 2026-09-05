"""Wer sieht welche Objekte (SPEC 2).

Eine Regel, an einer Stelle. Alle datenliefernden Pfade gehen hierüber --
Dashboard, Detailseiten, Wochenmail, Kalender, CSV und die Abhakmarken.

Holen und Prüfen sind bewusst zusammengelegt: Solange sie getrennte Schritte
sind, kann man das Prüfen vergessen.

Fremde Objekte ergeben 404, nicht 403. Ein "darauf hast du keine Berechtigung"
bestätigt, dass es das Objekt gibt.
"""

from django.shortcuts import get_object_or_404

from .models import Aufgabe, Bereich, Objekt


def sichtbare_objekte(benutzer):
    """Alle Objekte bei Verwaltungsberechtigung, sonst die zugewiesenen."""
    if benutzer is None or not benutzer.is_authenticated:
        return Objekt.objects.none()
    if benutzer.is_staff:
        return Objekt.objects.all()
    return benutzer.zugewiesene_objekte.all()


def darf_sehen(benutzer, objekt) -> bool:
    if objekt is None:
        return False
    return sichtbare_objekte(benutzer).filter(pk=objekt.pk).exists()


def bereich_oder_404(benutzer, pk) -> Bereich:
    return get_object_or_404(
        Bereich.objects.select_related("objekt", "typ").filter(
            objekt__in=sichtbare_objekte(benutzer)
        ),
        pk=pk,
    )


def aufgabe_oder_404(benutzer, pk) -> Aufgabe:
    return get_object_or_404(
        Aufgabe.objects.select_related(
            "bereich__objekt", "bereich__typ", "taetigkeit"
        ).filter(bereich__objekt__in=sichtbare_objekte(benutzer)),
        pk=pk,
    )
