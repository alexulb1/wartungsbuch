"""Die Oberflaeche.

Serverseitig gerendert, ohne eigenes JavaScript. Der Stichtag laesst sich per
Abfrageparameter setzen -- das macht Vorschauen moeglich und die Tests
reproduzierbar, ohne an der Systemuhr zu drehen.
"""

import csv
import datetime as dt
from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import connections
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.views.decorators.http import require_POST

from django.utils.translation import gettext as _

from django.conf import settings

from .faelligkeit import VORSCHAU_TAGE, Status, bewerten, monate_addieren, uebersicht
from .kalender import feed
from .forms import AnmeldeForm, EreignisForm, ErledigenForm, ProfilForm, UnterlageForm
from .mail import adresse, senden
from .models import Anhang, Aufgabe, Benutzer, Bereich, Ereignis, Zugangsmarke, Zweck
from .anhaenge import anhaenge_speichern
from .einmalig import einmal_speichern
from .sichtbarkeit import (
    aufgabe_oder_404,
    bereich_oder_404,
    darf_sehen,
    ereignis_oder_404,
    objekt_oder_404,
    sichtbare_objekte,
)
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
    # Auch stillgelegte: Sonst könnte man sie nirgends zurückholen.
    for aufgabe in bereich.aufgaben.select_related("taetigkeit", "bereich__objekt"):
        letzte = aufgabe.ereignisse.order_by("-datum").values_list("datum", flat=True).first()
        aufgaben.append(bewerten(aufgabe, letzte, heute))
    aufgaben.sort(key=lambda eintrag: (not eintrag.aufgabe.aktiv, eintrag.faellig_am))

    historie = (
        bereich.ereignisse.select_related("taetigkeit", "erfasst_von")
        .prefetch_related("anhaenge")
        .order_by("-datum", "-erfasst_am")
    )
    # Unterlagen hängen am Bauteil, nicht an einem Vorgang.
    unterlagen = bereich.anhaenge.filter(ereignis__isnull=True).order_by("hochgeladen_am")
    return render(
        request,
        "wartung/bereich.html",
        {
            "bereich": bereich,
            "aufgaben": aufgaben,
            "historie": historie,
            "unterlagen": unterlagen,
            "heute": heute,
        },
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
            ereignis, neu = einmal_speichern(formular)
            if neu:
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
            ereignis, neu = einmal_speichern(formular)
            if neu:
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
            # Die Marke ist schon verbraucht, eine zweite Anfrage käme gar
            # nicht bis hierher -- die Kennung schadet trotzdem nicht.
            ereignis, _neu = einmal_speichern(formular)
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
            _("Anhänge"),
        ]
    )
    ereignisse = (
        Ereignis.objects.filter(bereich__objekt__in=sichtbare_objekte(request.user))
        .select_related("bereich__objekt", "bereich__typ", "taetigkeit", "erfasst_von")
        .prefetch_related("anhaenge")
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
                # Damit die Zuordnung erhalten bleibt, wenn nur die Tabelle
                # übrig ist.
                " | ".join(a.datei.name for a in ereignis.anhaenge.all()),
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


@login_required
def anhang_neu(request, pk):
    """Unterlagen zum Bauteil nachtragen."""
    bereich = bereich_oder_404(request.user, pk)

    if request.method == "POST":
        formular = UnterlageForm(request.POST, request.FILES)
        if formular.is_valid():
            anhaenge_speichern(
                formular.cleaned_data["anhaenge"],
                bereich,
                request.user,
                beschriftung=formular.cleaned_data["beschriftung"],
            )
            return redirect("wartung:bereich", pk=bereich.pk)
    else:
        formular = UnterlageForm()

    return render(request, "wartung/anhang_neu.html", {"bereich": bereich, "formular": formular})


@login_required
@require_POST
def anhang_loeschen(request, kennung):
    """Nur per POST: Ein Löschen darf nie an einem GET hängen, weil Vorschauen
    und Scanner Links abrufen -- derselbe Grund wie beim Abhaken."""
    geprueft = _anhang_oder_404(request.user, kennung)
    bereich_nummer = geprueft.bereich_id
    geprueft.delete()
    return redirect("wartung:bereich", pk=bereich_nummer)


# --- Aufgaben stilllegen und löschen --------------------------------------


@login_required
@require_POST
def aufgabe_stilllegen(request, pk):
    """Nimmt die Aufgabe aus Planung und Meldungen, ohne etwas zu verlieren."""
    aufgabe = aufgabe_oder_404(request.user, pk)
    aufgabe.aktiv = False
    aufgabe.save(update_fields=["aktiv"])
    return redirect("wartung:bereich", pk=aufgabe.bereich_id)


@login_required
@require_POST
def aufgabe_aufnehmen(request, pk):
    aufgabe = aufgabe_oder_404(request.user, pk)
    aufgabe.aktiv = True
    aufgabe.save(update_fields=["aktiv"])
    return redirect("wartung:bereich", pk=aufgabe.bereich_id)


@login_required
def aufgabe_loeschen(request, pk):
    """Mit Rückfrage: In einer Aufgabe steckt eine Festlegung, die man nicht in
    zehn Sekunden wiederherstellt. Die Zwischenseite nennt vorher, was
    dranhängt und was stehenbleibt."""
    aufgabe = aufgabe_oder_404(request.user, pk)

    if request.method == "POST":
        bereich_nummer = aufgabe.bereich_id
        # Die Ereignisse bleiben; sie verlieren nur den Verweis (SET_NULL).
        # Die Historie ist die Wahrheit und wird nicht umgeschrieben.
        aufgabe.delete()
        return redirect("wartung:bereich", pk=bereich_nummer)

    return render(
        request,
        "wartung/aufgabe_loeschen.html",
        {"aufgabe": aufgabe, "anzahl_ereignisse": aufgabe.ereignisse.count()},
    )


@login_required
def ereignis_loeschen(request, pk):
    """Der heikelste Löschvorgang: Ein Ereignis ist die einzige Wahrheit.

    Weil die Fälligkeit daraus berechnet wird, verschiebt sein Verschwinden
    rückwirkend den nächsten Termin — löscht man die jüngste Erledigung, kann
    eine Aufgabe schlagartig überfällig sein. Die Rückfrage rechnet das vorher
    aus, sonst wundert man sich hinterher über eine Wochenmail.
    """
    ereignis = ereignis_oder_404(request.user, pk)
    rueckweg = _rueckweg(request, ereignis)

    if request.method == "POST":
        # Anhänge wandern über das post_delete-Signal in den Papierkorb.
        ereignis.delete()
        return redirect(rueckweg)

    return render(
        request,
        "wartung/ereignis_loeschen.html",
        {
            "ereignis": ereignis,
            "anzahl_anhaenge": ereignis.anhaenge.count(),
            "danach": _faelligkeit_ohne(ereignis, stichtag(request)),
            "rueckweg": rueckweg,
        },
    )


def _rueckweg(request, ereignis):
    """Wohin es nach dem Löschen oder Abbrechen geht.

    Nur zurück in den Nachweis desselben Objekts, samt Zeitraum — alles andere
    führt zur Bereichsseite. Ein frei wählbares Ziel wäre eine offene
    Weiterleitung: Ein präparierter Link schickte einen danach sonstwohin.
    """
    angabe = request.POST.get("zurueck") or request.GET.get("zurueck") or ""
    teile = urlsplit(angabe)
    nachweis = reverse("wartung:nachweis", args=[ereignis.bereich.objekt_id])
    if teile.scheme or teile.netloc or teile.path != nachweis:
        return reverse("wartung:bereich", args=[ereignis.bereich_id])

    zeitraum = []
    for name, wert in parse_qsl(teile.query):
        if name not in ("von", "bis"):
            continue
        try:
            dt.date.fromisoformat(wert)
        except ValueError:
            continue
        zeitraum.append((name, wert))
    return nachweis + ("?" + urlencode(zeitraum) if zeitraum else "")


def _faelligkeit_ohne(ereignis, heute):
    """Wie die Aufgabe dastünde, wenn es dieses Ereignis nicht gäbe."""
    if ereignis.aufgabe is None:
        return None
    letzte = (
        ereignis.aufgabe.ereignisse.exclude(pk=ereignis.pk)
        .order_by("-datum")
        .values_list("datum", flat=True)
        .first()
    )
    return bewerten(ereignis.aufgabe, letzte, heute)


# --- Auswertungen ---------------------------------------------------------

#: Wie weit die Jahresvorschau reicht. Was danach kommt, gehört nicht hinein.
VORSCHAU_MONATE = 12


def _zeitpunkt(request, name):
    roh = request.GET.get(name)
    if not roh:
        return None
    try:
        return dt.date.fromisoformat(roh)
    except ValueError:
        # Unsinn im Adressfeld soll die Seite nicht zerreißen.
        return None


@login_required
def nachweis(request, pk):
    """Was an einem Objekt geschah — zusammenhängend und weitergebbar.

    Nach Bereich gegliedert, innerhalb chronologisch: Wer das Dokument in die
    Hand bekommt, fragt "was ist mit dem Dach?", nicht "was war im März".
    """
    objekt = objekt_oder_404(request.user, pk)
    von, bis = _zeitpunkt(request, "von"), _zeitpunkt(request, "bis")

    ereignisse = (
        Ereignis.objects.filter(bereich__objekt=objekt)
        .select_related("bereich__typ", "taetigkeit", "erfasst_von")
        .prefetch_related("anhaenge")
        .order_by("bereich__typ__sortierung", "bereich__bezeichnung", "datum")
    )
    if von:
        ereignisse = ereignisse.filter(datum__gte=von)
    if bis:
        ereignisse = ereignisse.filter(datum__lte=bis)

    gruppen, reihenfolge = {}, []
    gesamt = 0
    for ereignis in ereignisse:
        if ereignis.bereich_id not in gruppen:
            reihenfolge.append(ereignis.bereich_id)
            gruppen[ereignis.bereich_id] = {"bereich": ereignis.bereich, "zeilen": []}
        gruppen[ereignis.bereich_id]["zeilen"].append(ereignis)
        gesamt += ereignis.kosten or 0

    return render(
        request,
        "wartung/nachweis.html",
        {
            "objekt": objekt,
            "gruppen": [gruppen[nummer] for nummer in reihenfolge],
            "anzahl": len(ereignisse),
            "gesamtkosten": gesamt,
            "von": von,
            "bis": bis,
            "heute": timezone.localdate(),
            # Damit das Löschen einer Zeile hierher zurückführt, Zeitraum inklusive.
            "hier": request.get_full_path(),
        },
    )


@login_required
def jahresvorschau(request):
    """Was in den nächsten zwölf Monaten ansteht, nach Monat gruppiert.

    Überfälliges steht als eigener Block oben — sonst ginge es zwischen den
    Monaten unter.
    """
    heute = stichtag(request)
    grenze = monate_addieren(heute, VORSCHAU_MONATE)

    eintraege = uebersicht(heute=heute, fuer=request.user)
    drängend = [e for e in eintraege if e.faellig_am <= heute]
    kommend = [e for e in eintraege if heute < e.faellig_am <= grenze]

    monate, reihenfolge = {}, []
    for eintrag in kommend:
        schluessel = (eintrag.faellig_am.year, eintrag.faellig_am.month)
        if schluessel not in monate:
            reihenfolge.append(schluessel)
            monate[schluessel] = {"erster": eintrag.faellig_am.replace(day=1), "zeilen": []}
        monate[schluessel]["zeilen"].append(eintrag)

    return render(
        request,
        "wartung/jahresvorschau.html",
        {
            "draengend": drängend,
            "monate": [monate[s] for s in sorted(reihenfolge)],
            "heute": heute,
            "bis": grenze,
        },
    )
