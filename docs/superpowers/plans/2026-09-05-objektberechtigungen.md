# Objektbezogene Berechtigungen — Umsetzungsplan

> **Für agentische Bearbeiter:** ERFORDERLICHE UNTER-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Aufgabe für Aufgabe umzusetzen. Die Schritte nutzen Checkbox-Syntax (`- [ ]`).

**Ziel:** Personen werden einzelnen Objekten zugewiesen und sehen nur diese samt Bereichen, Aufgaben und Ereignissen; ohne Zuweisung ist nichts sichtbar.

**Architektur:** Eine M:N-Beziehung `Benutzer.zugewiesene_objekte`. Ein Modul `wartung/sichtbarkeit.py` bündelt die Regel; alle neun datenliefernden Stellen gehen darüber. Holen und Prüfen sind in `bereich_oder_404` / `aufgabe_oder_404` zusammengelegt, damit das Prüfen nicht vergessen werden kann. Ein Wächter-Test liest die URL-Konfiguration selbst aus.

**Technik:** Django 5.2 LTS, Python 3.13, PostgreSQL. Keine neuen Abhängigkeiten.

**Spezifikation:** `docs/superpowers/specs/2026-09-05-objektberechtigungen-design.md`

## Globale Randbedingungen

- **Testgetrieben.** Jede Produktionszeile entsteht nach einem Test, den man hat scheitern sehen. Keine Ausnahme.
- **Keine neuen Abhängigkeiten.** `requirements.txt` bleibt bei Django, psycopg, whitenoise, gunicorn.
- **Sprache:** Bezeichner, Kommentare und Oberflächentexte auf Deutsch. Neue Oberflächentexte in `{% translate %}` bzw. `gettext_lazy` fassen und in `locale/en` und `locale/sv` übersetzen.
- **Fremde Objekte ergeben 404, nie 403.**
- **Testlauf:** `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung`
- **Ausgangslage:** 157 Tests, alle grün. Nach jeder Aufgabe muss das wieder gelten.
- **Committen** am Ende jeder Aufgabe, Commit-Nachricht auf Deutsch, mit Trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Dateiübersicht

| Datei | Verantwortung |
|---|---|
| `wartung/sichtbarkeit.py` | **neu** — die Regel: wer sieht welche Objekte |
| `wartung/test_sichtbarkeit.py` | **neu** — Tests der Regel |
| `wartung/test_berechtigung.py` | **neu** — Wirkung an den Ansichten, Wächter-Test |
| `wartung/models/benutzer.py` | Feld `zugewiesene_objekte` |
| `wartung/faelligkeit.py` | `uebersicht(..., fuer=None)` |
| `wartung/views.py` | Neun Stellen filtern bzw. prüfen |
| `wartung/kalender.py` | `feed(..., fuer=None)` |
| `wartung/management/commands/wochenmail.py` | Übersicht je Empfänger |
| `wartung/models/zugang.py` | Berechtigung beim Einlösen erneut prüfen |
| `wartung/admin.py` | Zuweisung am Objekt und am Benutzer |
| `SPEC.md` | Abschnitt 2 und 7 nachführen |

---

### Aufgabe 1: Beziehung und Regel

**Dateien:**
- Ändern: `wartung/models/benutzer.py`
- Erstellen: `wartung/sichtbarkeit.py`
- Erstellen: `wartung/test_sichtbarkeit.py`
- Erstellen: `wartung/migrations/0007_benutzer_zugewiesene_objekte.py` (erzeugt)

**Schnittstellen:**
- Liefert: `sichtbare_objekte(benutzer) -> QuerySet[Objekt]`, `darf_sehen(benutzer, objekt) -> bool`, `bereich_oder_404(benutzer, pk) -> Bereich`, `aufgabe_oder_404(benutzer, pk) -> Aufgabe`

- [ ] **Schritt 1: Test schreiben**

`wartung/test_sichtbarkeit.py`:

```python
"""Tests der Sichtbarkeitsregel (SPEC 2).

Eine Berechtigung, die im Zweifel öffnet, ist keine: Ohne Zuweisung ist nichts
sichtbar. Verwaltungsberechtigte sehen alles.
"""

from django.http import Http404
from django.test import TestCase

from .models import (
    Aufgabe,
    Benutzer,
    Bereich,
    BereichsTyp,
    Einheit,
    Objekt,
    ObjektTyp,
    Taetigkeit,
)
from .sichtbarkeit import (
    aufgabe_oder_404,
    bereich_oder_404,
    darf_sehen,
    sichtbare_objekte,
)


class Bestand(TestCase):
    def setUp(self):
        objekt_typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        bereichs_typ = BereichsTyp.objects.create(schluessel="wp", name_de="Wärmepumpe")
        taetigkeit = Taetigkeit.objects.create(schluessel="filter", name_de="Luftfilter wechseln")

        self.haus = Objekt.objects.create(name="Haupthaus", typ=objekt_typ)
        self.sommerhaus = Objekt.objects.create(name="Sommerhaus", typ=objekt_typ)
        self.bereich_haus = Bereich.objects.create(objekt=self.haus, typ=bereichs_typ)
        self.bereich_sommer = Bereich.objects.create(objekt=self.sommerhaus, typ=bereichs_typ)
        self.aufgabe_sommer = Aufgabe.objects.create(
            bereich=self.bereich_sommer,
            taetigkeit=taetigkeit,
            intervall_wert=30,
            intervall_einheit=Einheit.TAGE,
        )

        self.verwaltung = Benutzer.objects.create_user("chef@example.org", is_staff=True)
        self.betreuer = Benutzer.objects.create_user("hilfe@example.org")
        self.betreuer.zugewiesene_objekte.add(self.haus)
        self.fremder = Benutzer.objects.create_user("fremd@example.org")


class SichtbareObjekteTest(Bestand):
    def test_verwaltung_sieht_alles(self):
        self.assertEqual(sichtbare_objekte(self.verwaltung).count(), 2)

    def test_zugewiesener_sieht_nur_seins(self):
        self.assertEqual(list(sichtbare_objekte(self.betreuer)), [self.haus])

    def test_ohne_zuweisung_nichts(self):
        self.assertEqual(list(sichtbare_objekte(self.fremder)), [])

    def test_zuweisung_laesst_sich_entziehen(self):
        self.betreuer.zugewiesene_objekte.remove(self.haus)
        self.assertEqual(list(sichtbare_objekte(self.betreuer)), [])


class DarfSehenTest(Bestand):
    def test_verwaltung_darf_alles(self):
        self.assertTrue(darf_sehen(self.verwaltung, self.sommerhaus))

    def test_zugewiesener_darf_seins(self):
        self.assertTrue(darf_sehen(self.betreuer, self.haus))

    def test_zugewiesener_darf_fremdes_nicht(self):
        self.assertFalse(darf_sehen(self.betreuer, self.sommerhaus))


class HolenUndPruefenTest(Bestand):
    """Holen und Prüfen sind zusammengelegt -- getrennt kann man das Prüfen
    vergessen."""

    def test_bereich_wird_geliefert(self):
        self.assertEqual(bereich_oder_404(self.betreuer, self.bereich_haus.pk), self.bereich_haus)

    def test_fremder_bereich_ergibt_404(self):
        with self.assertRaises(Http404):
            bereich_oder_404(self.betreuer, self.bereich_sommer.pk)

    def test_fremde_aufgabe_ergibt_404(self):
        with self.assertRaises(Http404):
            aufgabe_oder_404(self.betreuer, self.aufgabe_sommer.pk)

    def test_verwaltung_bekommt_auch_fremdes(self):
        self.assertEqual(
            aufgabe_oder_404(self.verwaltung, self.aufgabe_sommer.pk), self.aufgabe_sommer
        )

    def test_unbekannte_nummer_ergibt_404(self):
        with self.assertRaises(Http404):
            bereich_oder_404(self.verwaltung, 999999)
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung.test_sichtbarkeit`
Erwartet: `ImportError: cannot import name 'sichtbare_objekte'` — das Modul gibt es noch nicht.

- [ ] **Schritt 3: Feld am Benutzer ergänzen**

In `wartung/models/benutzer.py`, direkt vor `kalender_schluessel`:

```python
    zugewiesene_objekte = models.ManyToManyField(
        "wartung.Objekt",
        related_name="betreuer",
        blank=True,
        verbose_name=_("zugewiesene Objekte"),
        help_text=_(
            "Wer hier zugewiesen ist, sieht dieses Objekt samt Bereichen, Aufgaben "
            "und Ereignissen. Verwaltungsberechtigte sehen ohnehin alles."
        ),
    )
```

- [ ] **Schritt 4: Migration erzeugen und anwenden**

```bash
DJANGO_DEBUG=1 .venv/bin/python manage.py makemigrations wartung && DJANGO_DEBUG=1 .venv/bin/python manage.py migrate
```

Erwartet: `0007_benutzer_zugewiesene_objekte`, danach `Applying … OK`.

- [ ] **Schritt 5: Modul schreiben**

`wartung/sichtbarkeit.py`:

```python
"""Wer sieht welche Objekte (SPEC 2).

Eine Regel, an einer Stelle. Alle datenliefernden Pfade gehen hierüber --
Dashboard, Detailseiten, Wochenmail, Kalender, CSV und die Abhakmarken.

Holen und Prüfen sind bewusst zusammengelegt: Solange sie getrennte Schritte
sind, kann man das Prüfen vergessen.

Fremde Objekte ergeben 404, nicht 403. Ein "darauf hast du keine Berechtigung"
bestätigt, dass es das Objekt gibt.
"""

from django.http import Http404
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
```

- [ ] **Schritt 6: Tests laufen lassen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung`
Erwartet: alle grün, jetzt 170 Tests.

- [ ] **Schritt 7: Committen**

```bash
git add wartung/sichtbarkeit.py wartung/test_sichtbarkeit.py wartung/models/benutzer.py wartung/migrations/
git commit -m "Sichtbarkeitsregel und Zuweisung von Objekten an Personen

Eine M:N-Beziehung am Benutzer und ein Modul, das die Regel bündelt. Holen und
Prüfen sind zusammengelegt, damit das Prüfen nicht vergessen werden kann.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Aufgabe 2: Fälligkeitsübersicht einschränken

**Dateien:**
- Ändern: `wartung/faelligkeit.py:139-160` (`uebersicht`)
- Ändern: `wartung/test_faelligkeit.py` (anhängen)

**Schnittstellen:**
- Verbraucht: `sichtbare_objekte` aus Aufgabe 1
- Liefert: `uebersicht(heute, vorschau_tage=VORSCHAU_TAGE, nur_meldbare=False, fuer=None)` — `fuer=None` bedeutet unverändert „alles", damit bestehende Aufrufer weiterlaufen

- [ ] **Schritt 1: Test schreiben**

An `wartung/test_faelligkeit.py` anhängen:

```python
class UebersichtSichtbarkeitTest(TestCase):
    """Die Übersicht liefert nur, was der Betrachter sehen darf (SPEC 2)."""

    def setUp(self):
        from .models import Benutzer

        self.eigene = _aufgabe(30, Einheit.TAGE, schluessel="eigene")
        self.fremde = _aufgabe(30, Einheit.TAGE, schluessel="fremde", objektname="Sommerhaus")
        self.betreuer = Benutzer.objects.create_user("hilfe@example.org")
        self.betreuer.zugewiesene_objekte.add(self.eigene.bereich.objekt)

    def test_ohne_angabe_unveraendert_alles(self):
        self.assertEqual(len(uebersicht(heute=datum("2026-03-10"))), 2)

    def test_fuer_betreuer_nur_zugewiesenes(self):
        eintraege = uebersicht(heute=datum("2026-03-10"), fuer=self.betreuer)
        self.assertEqual([e.aufgabe.pk for e in eintraege], [self.eigene.pk])

    def test_fuer_unbeteiligten_nichts(self):
        from .models import Benutzer

        fremder = Benutzer.objects.create_user("fremd@example.org")
        self.assertEqual(uebersicht(heute=datum("2026-03-10"), fuer=fremder), [])

    def test_verwaltung_sieht_weiterhin_alles(self):
        from .models import Benutzer

        chef = Benutzer.objects.create_user("chef@example.org", is_staff=True)
        self.assertEqual(len(uebersicht(heute=datum("2026-03-10"), fuer=chef)), 2)

    def test_bleibt_bei_einer_abfrage(self):
        with self.assertNumQueries(1):
            uebersicht(heute=datum("2026-03-10"), fuer=self.betreuer)
```

Die Hilfsfunktion `_aufgabe` am Ende derselben Datei braucht dafür einen Objektnamen. Ersetze ihre Signaturzeile

```python
    schluessel=None,
    speichern=True,
):
```

durch

```python
    schluessel=None,
    objektname="Haupthaus",
    speichern=True,
):
```

und die Objektzeile

```python
    objekt, _ = Objekt.objects.get_or_create(
        name="Haupthaus",
```

durch

```python
    objekt, _ = Objekt.objects.get_or_create(
        name=objektname,
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung.test_faelligkeit.UebersichtSichtbarkeitTest`
Erwartet: `TypeError: uebersicht() got an unexpected keyword argument 'fuer'`

- [ ] **Schritt 3: Umsetzen**

In `wartung/faelligkeit.py` die Signatur erweitern:

```python
def uebersicht(
    heute: dt.date,
    vorschau_tage: int = VORSCHAU_TAGE,
    nur_meldbare: bool = False,
    fuer=None,
) -> list[Faelligkeit]:
```

und im Rumpf hinter der `annotate`-Zeile ergänzen:

```python
    if fuer is not None:
        from .sichtbarkeit import sichtbare_objekte

        aufgaben = aufgaben.filter(bereich__objekt__in=sichtbare_objekte(fuer))
```

Der Import steht bewusst in der Funktion: `sichtbarkeit` importiert `models`, und ein Import auf Modulebene würde einen Ringschluss erzeugen.

Ergänze im Docstring der Funktion nach der bestehenden Erklärung:

```
    "fuer" schränkt auf die Objekte ein, die diese Person sehen darf. Ohne
    Angabe bleibt es bei allem -- das ist der Weg für Verwaltungsaufgaben, die
    ohne Benutzer laufen.
```

- [ ] **Schritt 4: Tests laufen lassen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung`
Erwartet: alle grün.

- [ ] **Schritt 5: Committen**

```bash
git add wartung/faelligkeit.py wartung/test_faelligkeit.py
git commit -m "Fälligkeitsübersicht kennt den Betrachter

uebersicht(..., fuer=benutzer) schränkt auf sichtbare Objekte ein. Ohne
Angabe unverändert alles, damit Verwaltungsaufgaben ohne Benutzer laufen.
Ein Test hält fest, dass es bei einer Abfrage bleibt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Aufgabe 3: Ansichten einschränken

**Dateien:**
- Ändern: `wartung/views.py` — `dashboard` (52), `bereich` (75), `erledigen` (98), `aufgaben_ergaenzen` (121), `ereignis_neu` (148), `kalender` (293), `export_csv` (305)
- Ändern: `wartung/kalender.py` — `feed`
- Erstellen: `wartung/test_berechtigung.py`

**Schnittstellen:**
- Verbraucht: `sichtbare_objekte`, `bereich_oder_404`, `aufgabe_oder_404` aus Aufgabe 1; `uebersicht(..., fuer=)` aus Aufgabe 2
- Liefert: `feed(heute=None, fuer=None) -> str`

- [ ] **Schritt 1: Test schreiben**

`wartung/test_berechtigung.py`:

```python
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


class Zwei_Objekte(TestCase):
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


class DashboardTest(Zwei_Objekte):
    def test_zeigt_nur_zugewiesenes(self):
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertContains(antwort, "Haupthaus")
        self.assertNotContains(antwort, "Sommerhaus")

    def test_ohne_zuweisung_leer(self):
        self.betreuer.zugewiesene_objekte.clear()
        antwort = self.client.get(reverse("wartung:dashboard"))
        self.assertNotContains(antwort, "Haupthaus")
        self.assertNotContains(antwort, "Sommerhaus")


class DetailseitenTest(Zwei_Objekte):
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


class AusgabenTest(Zwei_Objekte):
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


class VerwaltungTest(Zwei_Objekte):
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
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung.test_berechtigung`
Erwartet: Fehlschläge in `DashboardTest`, `DetailseitenTest`, `AusgabenTest` — die Ansichten filtern noch nicht. `VerwaltungTest` ist bereits grün.

- [ ] **Schritt 3: Ansichten umstellen**

In `wartung/views.py` den Import ergänzen, hinter `from .models import …`:

```python
from .sichtbarkeit import aufgabe_oder_404, bereich_oder_404, sichtbare_objekte
```

`dashboard`: die Zeile

```python
    eintraege = uebersicht(heute=heute)
```

wird zu

```python
    eintraege = uebersicht(heute=heute, fuer=request.user)
```

`bereich`: die Zeilen

```python
    bereich = get_object_or_404(
        Bereich.objects.select_related("objekt", "typ"), pk=pk
    )
```

werden zu

```python
    bereich = bereich_oder_404(request.user, pk)
```

`erledigen`: die Zeilen

```python
    aufgabe = get_object_or_404(
        Aufgabe.objects.select_related("bereich__objekt", "bereich__typ", "taetigkeit"), pk=pk
    )
```

werden zu

```python
    aufgabe = aufgabe_oder_404(request.user, pk)
```

`aufgaben_ergaenzen` und `ereignis_neu`: jeweils die Zeile

```python
    bereich = get_object_or_404(Bereich.objects.select_related("objekt", "typ"), pk=pk)
```

wird zu

```python
    bereich = bereich_oder_404(request.user, pk)
```

`kalender`: die Zeile

```python
        inhalt = feed(stichtag(request))
```

wird zu

```python
        inhalt = feed(stichtag(request), fuer=benutzer)
```

`export_csv`: die Zeilen

```python
    ereignisse = Ereignis.objects.select_related(
        "bereich__objekt", "bereich__typ", "taetigkeit", "erfasst_von"
    ).order_by("datum")
```

werden zu

```python
    ereignisse = (
        Ereignis.objects.filter(bereich__objekt__in=sichtbare_objekte(request.user))
        .select_related("bereich__objekt", "bereich__typ", "taetigkeit", "erfasst_von")
        .order_by("datum")
    )
```

- [ ] **Schritt 4: Kalenderfeed umstellen**

In `wartung/kalender.py` die Signatur

```python
def feed(heute: dt.date | None = None) -> str:
```

wird zu

```python
def feed(heute: dt.date | None = None, fuer=None) -> str:
```

und die Schleifenzeile

```python
    for eintrag in uebersicht(heute=heute):
```

wird zu

```python
    for eintrag in uebersicht(heute=heute, fuer=fuer):
```

- [ ] **Schritt 5: Tests laufen lassen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung`
Erwartet: alle grün.

- [ ] **Schritt 6: Committen**

```bash
git add wartung/views.py wartung/kalender.py wartung/test_berechtigung.py
git commit -m "Ansichten, Kalender und CSV auf sichtbare Objekte einschränken

Dashboard, Detailseiten, Katalogvorschläge, freies Ereignis, Kalenderfeed und
CSV-Ausgabe gehen jetzt über die Sichtbarkeitsregel. Fremdes ergibt 404, nicht
403 — eine Berechtigungsmeldung bestätigt die Existenz des Objekts.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Aufgabe 4: Wochenmail und Abhakmarken

**Dateien:**
- Ändern: `wartung/management/commands/wochenmail.py`
- Ändern: `wartung/models/zugang.py` (`einloesen`, `pruefen`)
- Ändern: `wartung/test_berechtigung.py` (anhängen)

**Schnittstellen:**
- Verbraucht: `uebersicht(..., fuer=)` aus Aufgabe 2, `darf_sehen` aus Aufgabe 1

- [ ] **Schritt 1: Test schreiben**

An `wartung/test_berechtigung.py` anhängen:

```python
class WochenmailTest(Zwei_Objekte):
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


class MarkeNachEntzugTest(Zwei_Objekte):
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
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung.test_berechtigung.WochenmailTest wartung.test_berechtigung.MarkeNachEntzugTest`
Erwartet: Fehlschläge in beiden Klassen außer `test_marke_wirkt_solange_die_zuweisung_besteht` und `test_bestehende_ereignisse_bleiben_nach_entzug`.

- [ ] **Schritt 3: Wochenmail je Empfänger berechnen**

In `wartung/management/commands/wochenmail.py` wird der Abschnitt

```python
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
```

ersetzt durch

```python
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
```

Im selben Rumpf wird der Aufruf

```python
                    "anzahl": len(eintraege),
```

beibehalten, und der Abschlussblock

```python
        if optionen["geplant"] and not optionen["probe"]:
```

bleibt unverändert; nur die beiden Vorkommen von `len(eintraege)` darin werden zu `gesamt`:

```python
            Mailversand.objects.update_or_create(
                woche=wochenkennung(jetzt),
                defaults={"anzahl_mails": verschickt, "anzahl_eintraege": gesamt},
            )

        self.stdout.write(
            self.style.SUCCESS(f"{verschickt} Mail(s) mit {gesamt} Eintrag/Einträgen.")
        )
```

- [ ] **Schritt 4: Marken beim Einlösen erneut prüfen**

In `wartung/models/zugang.py` in `ZugangsmarkenManager` eine Hilfsmethode ergänzen, direkt vor `einloesen`:

```python
    def _noch_berechtigt(self, marke) -> bool:
        """Eine Marke taugt nur so lange, wie ihr Empfänger das Objekt sehen darf.

        Sonst wirkte ein Entzug erst, wenn die Marke abläuft -- und das würde im
        Ernstfall niemand erklären können (SPEC 2).
        """
        if marke.aufgabe_id is None:
            return True
        from ..sichtbarkeit import darf_sehen

        return darf_sehen(marke.benutzer, marke.aufgabe.bereich.objekt)
```

In `einloesen` hinter

```python
        if marke is None:
            return None
```

einfügen:

```python
        if not self._noch_berechtigt(marke):
            return None
```

In `pruefen` wird der `return`-Ausdruck

```python
        return (
            self.filter(
                schluessel_hash=_hashen(roh),
                zweck=zweck,
                verbraucht_am__isnull=True,
                gueltig_bis__gt=timezone.now(),
            )
            .select_related("benutzer", "aufgabe__bereich__objekt", "aufgabe__taetigkeit")
            .first()
        )
```

ersetzt durch

```python
        marke = (
            self.filter(
                schluessel_hash=_hashen(roh),
                zweck=zweck,
                verbraucht_am__isnull=True,
                gueltig_bis__gt=timezone.now(),
            )
            .select_related("benutzer", "aufgabe__bereich__objekt", "aufgabe__taetigkeit")
            .first()
        )
        if marke is None or not self._noch_berechtigt(marke):
            return None
        return marke
```

- [ ] **Schritt 5: Tests laufen lassen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung`
Erwartet: alle grün.

- [ ] **Schritt 6: Committen**

```bash
git add wartung/management/commands/wochenmail.py wartung/models/zugang.py wartung/test_berechtigung.py
git commit -m "Wochenmail und Abhakmarken folgen der Berechtigung

Die Wochenmail wird je Empfänger berechnet; wer nichts zugewiesen hat, bekommt
keine. Abhakmarken werden beim Einlösen erneut geprüft — ein Entzug wirkt
sofort statt erst nach zehn Tagen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Aufgabe 5: Wächter-Test

**Dateien:**
- Ändern: `wartung/test_berechtigung.py` (anhängen)

**Schnittstellen:**
- Verbraucht: nichts Neues; liest `wartung.urls` aus

- [ ] **Schritt 1: Test schreiben**

An `wartung/test_berechtigung.py` anhängen:

```python
class WaechterTest(Zwei_Objekte):
    """Geht alle Adressen mit Objektbezug durch und prüft, dass ein fremdes
    Objekt nirgends durchkommt.

    Zweck ist ausdrücklich, künftige Lücken zu verhindern: Eine neue Ansicht,
    die den Filter vergisst, lässt diesen Test umfallen, ohne dass jemand daran
    denken muss. Kommt eine Route mit Objektbezug hinzu, gehört sie hier
    eingetragen -- der Test besteht darauf.
    """

    #: Routenname -> Kennzahl des fremden Objekts, die eingesetzt wird.
    ROUTEN_MIT_OBJEKTBEZUG = {
        "bereich": "bereich_sommer",
        "aufgaben_ergaenzen": "bereich_sommer",
        "ereignis_neu": "bereich_sommer",
        "erledigen": "aufgabe_sommer",
    }

    #: Routen ohne Objektbezug -- sie brauchen keine Prüfung.
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
```

- [ ] **Schritt 2: Test laufen lassen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung.test_berechtigung.WaechterTest`
Erwartet: grün — die Absicherung ist in Aufgabe 3 entstanden. Schlägt `test_alle_routen_sind_eingeordnet` fehl, ist eine Route nicht eingeordnet; sie gehört in eine der beiden Mengen.

- [ ] **Schritt 3: Wächter absichtlich brechen, um ihn zu prüfen**

Ein Test, der nie scheitert, prüft nichts. In `wartung/views.py` die Zeile in `bereich`

```python
    bereich = bereich_oder_404(request.user, pk)
```

vorübergehend ersetzen durch

```python
    bereich = get_object_or_404(Bereich.objects.select_related("objekt", "typ"), pk=pk)
```

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung.test_berechtigung.WaechterTest`
Erwartet: FEHLSCHLAG bei `route='bereich'`.

Danach die Zeile wieder zurückändern und den Test erneut laufen lassen — er muss wieder grün sein.

- [ ] **Schritt 4: Committen**

```bash
git add wartung/test_berechtigung.py
git commit -m "Wächter-Test über alle Routen mit Objektbezug

Liest die URL-Konfiguration selbst aus und besteht darauf, dass jede Route
eingeordnet ist. Eine künftige Ansicht, die den Filter vergisst, lässt ihn
umfallen, ohne dass jemand daran denken muss.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Aufgabe 6: Zuweisen im Admin

**Dateien:**
- Ändern: `wartung/admin.py` — `BenutzerAdmin`, `ObjektAdmin`
- Ändern: `wartung/test_oberflaeche.py` (anhängen)

- [ ] **Schritt 1: Test schreiben**

An `wartung/test_oberflaeche.py` anhängen:

```python
class ZuweisungImAdminTest(TestCase):
    def setUp(self):
        self.chef = Benutzer.objects.create_user("chef@example.org", is_staff=True, is_superuser=True)
        self.client.force_login(self.chef)
        typ = ObjektTyp.objects.create(schluessel="haus", name_de="Haus")
        self.objekt = Objekt.objects.create(name="Haupthaus", typ=typ)
        self.betreuer = Benutzer.objects.create_user("hilfe@example.org", name="Hilfe")

    def test_objektseite_bietet_die_zuweisung_an(self):
        antwort = self.client.get(f"/admin/wartung/objekt/{self.objekt.pk}/change/")
        self.assertContains(antwort, "Betreut von")

    def test_benutzerseite_bietet_die_zuweisung_an(self):
        antwort = self.client.get(f"/admin/wartung/benutzer/{self.betreuer.pk}/change/")
        self.assertContains(antwort, "zugewiesene_objekte")

    def test_uebersicht_zeigt_die_anzahl_der_objekte(self):
        self.betreuer.zugewiesene_objekte.add(self.objekt)
        antwort = self.client.get("/admin/wartung/benutzer/")
        self.assertEqual(antwort.status_code, 200)
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung.test_oberflaeche.ZuweisungImAdminTest`
Erwartet: Fehlschlag in den ersten beiden Tests — die Felder sind noch nicht eingebunden.

- [ ] **Schritt 3: Admin ergänzen**

In `wartung/admin.py` in `BenutzerAdmin` die beiden Zeilen

```python
    list_display = ["email", "name", "sprache", "is_active", "is_staff"]
```

und

```python
    fields = ["email", "name", "sprache", "is_active", "is_staff", "is_superuser", "groups"]
    filter_horizontal = ["groups"]
```

ersetzen durch

```python
    list_display = ["email", "name", "sprache", "anzahl_objekte", "is_active", "is_staff"]
```

und

```python
    fields = [
        "email",
        "name",
        "sprache",
        "zugewiesene_objekte",
        "is_active",
        "is_staff",
        "is_superuser",
        "groups",
    ]
    filter_horizontal = ["groups", "zugewiesene_objekte"]

    @admin.display(description=_("Objekte"))
    def anzahl_objekte(self, benutzer):
        if benutzer.is_staff:
            return _("alle")
        return benutzer.zugewiesene_objekte.count()
```

In `wartung/admin.py` vor `ObjektAdmin` ein Inline ergänzen:

```python
class BetreuerInline(admin.TabularInline):
    """Die Zuordnung liegt am Benutzer; hier von der Objektseite aus bearbeitbar.

    Ein Inline über die Zwischentabelle, weil ``filter_horizontal`` auf einer
    umgekehrten M:N-Beziehung nicht arbeitet.
    """

    model = Benutzer.zugewiesene_objekte.through
    extra = 0
    verbose_name = _("Betreut von")
    verbose_name_plural = _("Betreut von")
    autocomplete_fields = ["benutzer"]
```

In `ObjektAdmin` die Zeile

```python
    inlines = [BereichInline]
```

ersetzen durch

```python
    inlines = [BereichInline, BetreuerInline]
```

- [ ] **Schritt 4: Tests laufen lassen**

Ausführen: `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung`
Erwartet: alle grün. Schlägt `test_objektseite_bietet_die_zuweisung_an` fehl, prüfe, ob das Inline eingebunden ist.

- [ ] **Schritt 5: Committen**

```bash
git add wartung/admin.py wartung/test_oberflaeche.py
git commit -m "Objekte im Admin an Personen zuweisen

Am Objekt als Inline "Betreut von", am Benutzer als Doppelliste. Dieselbe
Zuordnung, zwei Blickrichtungen. Die Benutzerübersicht zeigt, wie viele
Objekte jemand sieht.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Aufgabe 7: Übersetzungen und Spezifikation nachführen

**Dateien:**
- Ändern: `locale/en/LC_MESSAGES/django.po`, `locale/sv/LC_MESSAGES/django.po`
- Ändern: `SPEC.md`
- Ändern: `README.md`

- [ ] **Schritt 1: Neue Texte einsammeln**

```bash
DJANGO_DEBUG=1 .venv/bin/python manage.py makemessages -l en -l sv --no-location --no-wrap -i ".venv/*"
```

- [ ] **Schritt 2: Übersetzungen eintragen**

Die neuen Einträge sind:

| Deutsch | Englisch | Schwedisch |
|---|---|---|
| `zugewiesene Objekte` | `assigned properties` | `tilldelade fastigheter` |
| `Wer hier zugewiesen ist, sieht dieses Objekt samt Bereichen, Aufgaben und Ereignissen. Verwaltungsberechtigte sehen ohnehin alles.` | `Whoever is assigned here sees this property with its areas, tasks and events. Administrators see everything anyway.` | `Den som tilldelas här ser fastigheten med dess byggnadsdelar, uppgifter och händelser. Administratörer ser allt ändå.` |
| `Betreut von` | `Looked after by` | `Sköts av` |
| `Objekte` | `Properties` | `Fastigheter` |
| `alle` | `all` | `alla` |

**Achtung fuzzy:** `msgmerge` markiert ähnliche Einträge als `#, fuzzy` und rät eine Übersetzung; `msgfmt` übergeht solche Einträge, und die Oberfläche zeigt still Deutsch. Entferne alle `fuzzy`-Markierungen der neuen Einträge und trage die Übersetzung von Hand ein. `wartung/test_sprachdateien.py` wacht darüber.

- [ ] **Schritt 3: Übersetzen und prüfen**

```bash
DJANGO_DEBUG=1 .venv/bin/python manage.py compilemessages --ignore .venv && DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung
```

Erwartet: alle grün, insbesondere `wartung.test_sprachdateien`.

- [ ] **Schritt 4: SPEC.md nachführen**

In `SPEC.md`, Abschnitt „## 2. Nutzer und Zugang", die Zeile

```
- Der Eigentümer und wenige Vertraute. Alle sehen und dürfen alles, keine Rollen.
```

ersetzen durch

```
- Der Eigentümer und wenige Vertraute.
- **Sichtbarkeit je Objekt:** Personen werden einzelnen Objekten zugewiesen und
  sehen nur diese samt Bereichen, Aufgaben und Ereignissen. Ohne Zuweisung ist
  nichts sichtbar. Wer Verwaltungsberechtigung hat, sieht alles.
- Eine Zuweisung gibt volle Rechte an diesem Objekt — sehen und eintragen. Das
  Objekt ist der Zaun, nicht die Tätigkeit.
```

In Abschnitt „### Bewusst nicht in Version 1" den Eintrag `Mieter- und Rollenverwaltung` ersetzen durch `Rollen unterhalb der Objektzuweisung (etwa nur-lesend)`.

In Abschnitt „## 7. Funktionsumfang Version 1" nach dem Punkt „Dashboard: was ist fällig, was ist überfällig" ergänzen:

```
- Zuweisung von Personen zu Objekten in der Verwaltung
```

In Abschnitt „## 11. Verworfene Alternativen und ihre Begründung" die Zeilen ergänzen:

```
| Rolle je Zuweisung (lesen / mitarbeiten) | Kein tatsächlicher Nur-Lesen-Fall; verdoppelt jede Zuweisungsentscheidung |
| Eigenes Kennzeichen „sieht alle Objekte" | Bei wenigen Objekten identisch mit „allen Objekten zugewiesen" |
| Berechtigungsbibliothek (django-guardian) | Eine Abhängigkeit auf zehn Jahre für eine Regel in dreißig Zeilen |
```

- [ ] **Schritt 5: README.md nachführen**

Im Abschnitt „## Aufbau" nach der Zeile für `wartung/versandplan.py` ergänzen:

```
wartung/sichtbarkeit.py      Wer sieht welche Objekte
```

Im Abschnitt „## Grundsätze" ergänzen:

```
- **Sichtbarkeit wird an einer Stelle entschieden.** Alle datenliefernden Pfade
  gehen über `sichtbarkeit.py`; ein Wächter-Test geht die Routen durch und
  besteht darauf, dass jede eingeordnet ist.
```

- [ ] **Schritt 6: Vollständiger Testlauf**

```bash
DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung && DJANGO_DEBUG=1 .venv/bin/python manage.py makemigrations --check --dry-run
```

Erwartet: alle grün, `No changes detected`.

- [ ] **Schritt 7: Committen**

```bash
git add locale SPEC.md README.md
git commit -m "Übersetzungen und Spezifikation für die Berechtigungen nachführen

SPEC.md Abschnitt 2 sagte "alle sehen und dürfen alles" — das gilt nicht mehr.
Ohne diese Nachführung widerspricht die Spezifikation dem Code.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Abnahme

Nach Aufgabe 7 muss gelten:

- [ ] `DJANGO_DEBUG=1 .venv/bin/python manage.py test wartung` — alle grün, rund 190 Tests
- [ ] `makemigrations --check --dry-run` meldet `No changes detected`
- [ ] Ein Konto ohne Zuweisung sieht ein leeres Dashboard, bekommt keine Wochenmail, einen leeren Kalender und eine CSV nur mit Kopfzeile
- [ ] Ein zugewiesenes Konto sieht sein Objekt und kann darin abhaken
- [ ] Ein Entzug entwertet eine ausgegebene Abhakmarke sofort
- [ ] `SPEC.md` und `README.md` widersprechen dem Code nicht mehr
