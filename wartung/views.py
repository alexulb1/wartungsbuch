"""Die Oberflaeche.

Serverseitig gerendert, ohne eigenes JavaScript. Der Stichtag laesst sich per
Abfrageparameter setzen -- das macht Vorschauen moeglich und die Tests
reproduzierbar, ohne an der Systemuhr zu drehen.
"""

import datetime as dt
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from .faelligkeit import Status, bewerten, uebersicht
from .forms import EreignisForm, ErledigenForm, ProfilForm
from .models import Aufgabe, Bereich, Ereignis


def stichtag(request) -> dt.date:
    roh = request.GET.get("stichtag")
    if roh:
        try:
            return dt.date.fromisoformat(roh)
        except ValueError:
            pass
    return timezone.localdate()


@login_required
def dashboard(request):
    heute = stichtag(request)
    eintraege = uebersicht(heute=heute)

    nach_objekt = defaultdict(list)
    for eintrag in eintraege:
        nach_objekt[eintrag.aufgabe.bereich.objekt].append(eintrag)

    # Objekte mit dem Draengendsten zuerst; ruhende ans Ende, weil dort gerade
    # nichts zu tun ist.
    gruppen = sorted(
        nach_objekt.items(),
        key=lambda paar: (not paar[1][0].wird_gemeldet, paar[1][0].faellig_am),
    )
    offen = [e for e in eintraege if e.status != Status.OFFEN]
    return render(
        request,
        "wartung/dashboard.html",
        {"gruppen": gruppen, "heute": heute, "anzahl_offen": len(offen)},
    )


@login_required
def bereich(request, pk):
    bereich = get_object_or_404(
        Bereich.objects.select_related("objekt", "typ"), pk=pk
    )
    heute = stichtag(request)
    aufgaben = []
    for aufgabe in bereich.aufgaben.filter(aktiv=True).select_related("taetigkeit", "bereich__objekt"):
        letzte = aufgabe.ereignisse.order_by("-datum").values_list("datum", flat=True).first()
        aufgaben.append(bewerten(aufgabe, letzte, heute))
    aufgaben.sort(key=lambda eintrag: eintrag.faellig_am)

    historie = (
        bereich.ereignisse.select_related("taetigkeit", "erfasst_von")
        .order_by("-datum", "-erfasst_am")
    )
    return render(
        request,
        "wartung/bereich.html",
        {"bereich": bereich, "aufgaben": aufgaben, "historie": historie, "heute": heute},
    )


@login_required
def erledigen(request, pk):
    aufgabe = get_object_or_404(
        Aufgabe.objects.select_related("bereich__objekt", "bereich__typ", "taetigkeit"), pk=pk
    )
    heute = stichtag(request)

    if request.method == "POST":
        # Aufgabe und Urheber gehoeren an das Ereignis, bevor validiert wird:
        # Bereich und Taetigkeit leiten sich daraus ab (SPEC 4).
        entwurf = Ereignis(aufgabe=aufgabe, erfasst_von=request.user)
        formular = ErledigenForm(request.POST, instance=entwurf)
        if formular.is_valid():
            formular.save()
            return redirect("wartung:bereich", pk=aufgabe.bereich_id)
    else:
        formular = ErledigenForm(initial={"datum": heute})

    return render(
        request, "wartung/erledigen.html", {"aufgabe": aufgabe, "formular": formular, "heute": heute}
    )


@login_required
def aufgaben_ergaenzen(request, pk):
    """Aufgaben aus dem Vorlagenkatalog uebernehmen (SPEC 7)."""
    bereich = get_object_or_404(Bereich.objects.select_related("objekt", "typ"), pk=pk)
    vorhanden = set(bereich.aufgaben.values_list("taetigkeit_id", flat=True))
    vorschlaege = bereich.typ.taetigkeiten.exclude(pk__in=vorhanden)

    if request.method == "POST":
        gewaehlt = vorschlaege.filter(pk__in=request.POST.getlist("taetigkeit"))
        for taetigkeit in gewaehlt:
            Aufgabe.objects.create(
                bereich=bereich,
                taetigkeit=taetigkeit,
                intervall_wert=taetigkeit.standard_intervall_wert or 12,
                intervall_einheit=taetigkeit.standard_intervall_einheit or "monate",
                modus=taetigkeit.standard_modus,
                kalender_monat=taetigkeit.standard_kalender_monat,
            )
        return redirect("wartung:bereich", pk=bereich.pk)

    return render(
        request,
        "wartung/aufgaben_ergaenzen.html",
        {"bereich": bereich, "vorschlaege": vorschlaege},
    )


@login_required
def ereignis_neu(request, pk):
    bereich = get_object_or_404(Bereich.objects.select_related("objekt", "typ"), pk=pk)
    heute = stichtag(request)

    if request.method == "POST":
        entwurf = Ereignis(bereich=bereich, erfasst_von=request.user)
        formular = EreignisForm(request.POST, instance=entwurf, bereich=bereich)
        if formular.is_valid():
            formular.save()
            return redirect("wartung:bereich", pk=bereich.pk)
    else:
        formular = EreignisForm(initial={"datum": heute}, bereich=bereich)

    return render(
        request, "wartung/ereignis_neu.html", {"bereich": bereich, "formular": formular}
    )


@login_required
def profil(request):
    if request.method == "POST":
        formular = ProfilForm(request.POST, instance=request.user)
        if formular.is_valid():
            formular.save()
            return redirect("wartung:profil")
    else:
        formular = ProfilForm(instance=request.user)
    return render(request, "wartung/profil.html", {"formular": formular})
