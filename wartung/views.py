"""Die Oberflaeche.

Serverseitig gerendert, ohne eigenes JavaScript. Der Stichtag laesst sich per
Abfrageparameter setzen -- das macht Vorschauen moeglich und die Tests
reproduzierbar, ohne an der Systemuhr zu drehen.
"""

import csv
import datetime as dt
from collections import defaultdict

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import connections
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation

from django.utils.translation import gettext as _

from django.conf import settings

from .faelligkeit import VORSCHAU_TAGE, Status, bewerten, uebersicht
from .kalender import feed
from .forms import AnmeldeForm, EreignisForm, ErledigenForm, ProfilForm
from .mail import adresse, senden
from .models import Anhang, Aufgabe, Benutzer, Bereich, Ereignis, Zugangsmarke, Zweck
from .anhaenge import anhaenge_speichern
from .sichtbarkeit import aufgabe_oder_404, bereich_oder_404, darf_sehen, sichtbare_objekte
from .models.zugang import GUELTIGKEIT_ANMELDUNG


def vorbelegung(benutzer, heute) -> dict:
    """Was ein neues Ereignisformular schon wissen kann.

    "ausgeführt von" meint, wer die Arbeit gemacht hat -- im Regelfall die
    Person, die gerade abhakt. Bleibt überschreibbar: Steht dort eine Firma,
    gehört die Firma hinein. Ohne hinterlegten Namen bleibt das Feld leer;
    ein Adressfragment wäre dort unsinnig.
    """
    return {"datum": heute, "ausgefuehrt_von": benutzer.name}


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
    alle_zeigen = request.GET.get("horizont") == "alle"
    horizont = None if alle_zeigen else settings.DASHBOARD_HORIZONT_TAGE

    eintraege = uebersicht(
        heute=heute,
        # Damit Anzeige und Beschriftung übereinstimmen: Was im Horizont liegt,
        # heißt auch "bald fällig" und nicht "offen".
        vorschau_tage=horizont or VORSCHAU_TAGE,
        fuer=request.user,
        horizont_tage=horizont,
    )
    spaeter = 0
    if not alle_zeigen:
        spaeter = len(uebersicht(heute=heute, fuer=request.user)) - len(eintraege)

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
        {
            "gruppen": gruppen,
            "heute": heute,
            "anzahl_offen": len(offen),
            "spaeter": spaeter,
            "alle_zeigen": alle_zeigen,
            "horizont": horizont,
        },
    )


@login_required
def bereich(request, pk):
    bereich = bereich_oder_404(request.user, pk)
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
    aufgabe = aufgabe_oder_404(request.user, pk)
    heute = stichtag(request)

    if request.method == "POST":
        # Aufgabe und Urheber gehoeren an das Ereignis, bevor validiert wird:
        # Bereich und Taetigkeit leiten sich daraus ab (SPEC 4).
        entwurf = Ereignis(aufgabe=aufgabe, erfasst_von=request.user)
        formular = ErledigenForm(request.POST, request.FILES, instance=entwurf)
        if formular.is_valid():
            ereignis = formular.save()
            anhaenge_speichern(
                formular.cleaned_data["anhaenge"], aufgabe.bereich, request.user, ereignis
            )
            return redirect("wartung:bereich", pk=aufgabe.bereich_id)
    else:
        formular = ErledigenForm(initial=vorbelegung(request.user, heute))

    return render(
        request, "wartung/erledigen.html", {"aufgabe": aufgabe, "formular": formular, "heute": heute}
    )


@login_required
def aufgaben_ergaenzen(request, pk):
    """Aufgaben aus dem Vorlagenkatalog uebernehmen (SPEC 7)."""
    bereich = bereich_oder_404(request.user, pk)
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
    bereich = bereich_oder_404(request.user, pk)
    heute = stichtag(request)

    if request.method == "POST":
        entwurf = Ereignis(bereich=bereich, erfasst_von=request.user)
        formular = EreignisForm(request.POST, request.FILES, instance=entwurf, bereich=bereich)
        if formular.is_valid():
            ereignis = formular.save()
            anhaenge_speichern(
                formular.cleaned_data["anhaenge"], bereich, request.user, ereignis
            )
            return redirect("wartung:bereich", pk=bereich.pk)
    else:
        formular = EreignisForm(initial=vorbelegung(request.user, heute), bereich=bereich)

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
    return render(
        request,
        "wartung/profil.html",
        {
            "formular": formular,
            "kalender_adresse": adresse(
                reverse("wartung:kalender", args=[request.user.kalender_schluessel])
            ),
        },
    )


# --- Anmeldung und Ein-Klick-Abhaken (SPEC 2, SPEC 6) --------------------

#: Wie viele Anmeldelinks je Konto in RATENFENSTER hoechstens verschickt werden.
RATE_HOECHSTZAHL = 3
RATENFENSTER = dt.timedelta(minutes=15)


def _gebremst(benutzer) -> bool:
    seit = timezone.now() - RATENFENSTER
    anzahl = Zugangsmarke.objects.filter(
        benutzer=benutzer, zweck=Zweck.ANMELDUNG, erstellt_am__gte=seit
    ).count()
    return anzahl >= RATE_HOECHSTZAHL


def anmelden(request):
    if request.user.is_authenticated:
        return redirect("wartung:dashboard")

    if request.method == "POST":
        formular = AnmeldeForm(request.POST)
        if formular.is_valid():
            benutzer = Benutzer.objects.filter(
                email__iexact=formular.cleaned_data["email"], is_active=True
            ).first()
            if benutzer is not None and not _gebremst(benutzer):
                _, roh = Zugangsmarke.objects.anlegen(Zweck.ANMELDUNG, benutzer)
                senden(
                    benutzer,
                    "wartung/mail/anmeldung_betreff.txt",
                    "wartung/mail/anmeldung.txt",
                    {
                        "benutzer": benutzer,
                        "link": adresse(reverse("wartung:anmelden_mit_marke", args=[roh])),
                        "stunden": int(GUELTIGKEIT_ANMELDUNG.total_seconds() // 3600),
                    },
                )
            # Dieselbe Antwort in jedem Fall: keine Auskunft darueber, wer ein
            # Konto hat.
            return render(request, "wartung/anmelden.html", {"verschickt": True})
    else:
        formular = AnmeldeForm()

    return render(request, "wartung/anmelden.html", {"formular": formular})


def anmelden_mit_marke(request, marke):
    eingeloest = Zugangsmarke.objects.einloesen(marke, Zweck.ANMELDUNG)
    if eingeloest is None:
        return render(request, "wartung/marke_ungueltig.html", status=400)
    login(request, eingeloest.benutzer, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("wartung:dashboard")


def abmelden(request):
    logout(request)
    return redirect("wartung:anmelden")


def erledigt_mit_marke(request, marke):
    """Abhaken direkt aus der Wochenmail, ohne Anmeldung.

    Der blosse Aufruf verbraucht die Marke nicht -- Mailprogramme und
    Virenscanner rufen Links vorab ab (SPEC 6).
    """
    if request.method == "POST":
        eingeloest = Zugangsmarke.objects.einloesen(marke, Zweck.ERLEDIGUNG)
        if eingeloest is None:
            raise Http404
        aufgabe = eingeloest.aufgabe
        entwurf = Ereignis(aufgabe=aufgabe, erfasst_von=eingeloest.benutzer)
        formular = ErledigenForm(request.POST, instance=entwurf, mit_anhaengen=False)
        if formular.is_valid():
            ereignis = formular.save()
            with translation.override(eingeloest.benutzer.sprache):
                return render(request, "wartung/erledigt_danke.html", {"ereignis": ereignis})
        # Ungueltige Eingabe: die Marke ist verbraucht, also eine neue ausgeben,
        # damit der Empfaenger nicht wegen eines Tippfehlers ausgesperrt bleibt.
        _, neuer_rohwert = Zugangsmarke.objects.anlegen(
            Zweck.ERLEDIGUNG, eingeloest.benutzer, aufgabe=aufgabe
        )
        return render(
            request,
            "wartung/erledigt_marke.html",
            {"aufgabe": aufgabe, "formular": formular, "marke": neuer_rohwert},
        )

    geprueft = Zugangsmarke.objects.pruefen(marke, Zweck.ERLEDIGUNG)
    if geprueft is None:
        raise Http404
    return render(
        request,
        "wartung/erledigt_marke.html",
        {
            "aufgabe": geprueft.aufgabe,
            "formular": ErledigenForm(
                initial=vorbelegung(geprueft.benutzer, timezone.localdate()),
                mit_anhaengen=False,
            ),
            "marke": marke,
        },
    )


# --- Kalenderfeed und CSV-Ausgabe (SPEC 7) -------------------------------


def kalender(request, schluessel):
    """Abonnierbarer Terminkalender. Der Schluessel steht in der Adresse --
    er gibt Termine preis, aber keinen Zugang zur Anwendung."""
    benutzer = get_object_or_404(Benutzer, kalender_schluessel=schluessel, is_active=True)
    with translation.override(benutzer.sprache):
        inhalt = feed(stichtag(request), fuer=benutzer)
    antwort = HttpResponse(inhalt, content_type="text/calendar; charset=utf-8")
    antwort["Content-Disposition"] = 'inline; filename="wartungsbuch.ics"'
    return antwort


@login_required
def export_csv(request):
    """Alle Ereignisse als Tabelle -- die Rückversicherung gegen den Tag, an
    dem diese Anwendung nicht mehr läuft (SPEC 7)."""
    antwort = HttpResponse(content_type="text/csv; charset=utf-8")
    heute = timezone.localdate().isoformat()
    antwort["Content-Disposition"] = f'attachment; filename="wartungsbuch-{heute}.csv"'
    antwort.write("﻿")  # Byte-Order-Mark, damit Tabellenkalkulationen UTF-8 erkennen

    schreiber = csv.writer(antwort, delimiter=";")
    schreiber.writerow(
        [
            _("Datum"),
            _("Objekt"),
            _("Bereich"),
            _("Tätigkeit"),
            _("Kosten"),
            _("ausgeführt von"),
            _("Notiz"),
            _("erfasst von"),
        ]
    )
    ereignisse = (
        Ereignis.objects.filter(bereich__objekt__in=sichtbare_objekte(request.user))
        .select_related("bereich__objekt", "bereich__typ", "taetigkeit", "erfasst_von")
        .order_by("datum")
    )
    for ereignis in ereignisse:
        schreiber.writerow(
            [
                ereignis.datum.isoformat(),
                ereignis.bereich.objekt.name,
                str(ereignis.bereich),
                ereignis.bezeichnung,
                ereignis.kosten if ereignis.kosten is not None else "",
                ereignis.ausgefuehrt_von,
                ereignis.notiz,
                ereignis.erfasst_von.email if ereignis.erfasst_von else "",
            ]
        )
    return antwort


def lebenszeichen(request):
    """Sagt, ob der Container arbeitsfähig ist -- für die Container-Prüfung.

    Bewusst wortkarg: Der Endpunkt ist offen, also gibt er nur Auskunft über
    die eigene Betriebsbereitschaft, nichts über den Bestand.
    """
    try:
        connections["default"].cursor().execute("SELECT 1")
    except Exception:
        return JsonResponse({"datenbank": "nicht erreichbar"}, status=503)
    return JsonResponse({"datenbank": "erreichbar"})


# --- Anhänge ausliefern ---------------------------------------------------


def _anhang_oder_404(benutzer, kennung) -> Anhang:
    """Holt den Anhang und prüft die Berechtigung in einem Schritt.

    Getrennt könnte man das Prüfen vergessen -- dieselbe Überlegung wie bei
    bereich_oder_404.
    """
    anhang = get_object_or_404(
        Anhang.objects.select_related("bereich__objekt"), kennung=kennung
    )
    if not darf_sehen(benutzer, anhang.bereich.objekt):
        raise Http404
    return anhang


@login_required
def anhang(request, kennung):
    geprueft = _anhang_oder_404(request.user, kennung)
    return FileResponse(
        geprueft.datei.open("rb"),
        content_type=geprueft.inhaltstyp or "application/octet-stream",
        filename=geprueft.dateiname,
    )


@login_required
def anhang_vorschau(request, kennung):
    geprueft = _anhang_oder_404(request.user, kennung)
    if not geprueft.vorschau:
        raise Http404
    return FileResponse(geprueft.vorschau.open("rb"), content_type="image/jpeg")
