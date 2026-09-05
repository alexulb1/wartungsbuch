# Objektbezogene Berechtigungen

*Abgestimmt am 05.09.2026. Ändert SPEC.md Abschnitt 2.*

## Anlass

SPEC.md hält bisher fest: „Du und wenige Vertraute. Alle sehen und dürfen
alles, keine Rollen." Das soll enger werden: Personen werden einzelnen
Objekten zugewiesen und sehen nur diese samt Bereichen, Aufgaben und
Ereignissen. Ohne Zuweisung ist nichts sichtbar.

## Entscheidungen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Was darf eine zugewiesene Person? | Volle Rechte an diesem Objekt — sehen und eintragen | Das Objekt ist der Zaun, nicht die Tätigkeit. Eine Wochenmail mit Abhaklinks an jemanden, der nicht abhaken darf, wäre eine Aufforderung ohne Handlungsmöglichkeit |
| Ohne Zuweisung? | Nichts sichtbar | Eine Berechtigung, die im Zweifel öffnet, ist keine |
| Wer sieht alles? | Wer Verwaltungsberechtigung hat | „Sieht alles" ist bei wenigen Objekten als „allen Objekten zugewiesen" ausdrückbar — ein Konzept weniger |
| Bereits verschickte Abhaklinks bei Entzug? | Werden beim Einlösen erneut geprüft und verweigert | Sonst wirkte ein Entzug erst nach zehn Tagen, und niemand würde das im Ernstfall erklären können |
| Ereignisse bei Entzug? | Bleiben bestehen, mit Namen | Die Historie ist die Wahrheit und wird nicht rückwirkend umgeschrieben |
| Vorlagenkatalog? | Bleibt für alle sichtbar | Wortschatz, kein Bestand — daran hängt keine Information über die Objekte |

### Verworfen

| Verworfen | Grund |
|---|---|
| Rolle je Zuweisung (lesen / mitarbeiten) | Kein tatsächlicher Nur-Lesen-Fall vorhanden; verdoppelt jede Zuweisungsentscheidung und jede Fallunterscheidung in den Ansichten |
| Eigenes Kennzeichen „sieht alle Objekte" | Bei zwei Objekten identisch mit „allen Objekten zugewiesen" |
| Berechtigungsbibliothek (django-guardian) | Eine Abhängigkeit auf zehn Jahre für eine Regel, die in dreißig Zeilen passt |
| Eigener Manager (`Objekt.objects.fuer(…)`) | Gleiche Vergessens-Schwäche wie die zentrale Funktion, ohne Vorteil |
| 403 statt 404 bei fremden Objekten | Ein „keine Berechtigung" bestätigt die Existenz des Objekts |

## Datenmodell

Eine Beziehung, kein neues Modell:

```
Benutzer  ←──── zugewiesene_objekte (M:N) ────→  Objekt
```

`Benutzer.zugewiesene_objekte = ManyToManyField("wartung.Objekt",
related_name="betreuer", blank=True)`

Bereiche, Aufgaben und Ereignisse hängen bereits am Objekt; ihre Sichtbarkeit
folgt daraus und braucht keine eigene Zuordnung.

## Die Regel

Neues Modul `wartung/sichtbarkeit.py`:

| Funktion | Verhalten |
|---|---|
| `sichtbare_objekte(benutzer)` | Alle Objekte, wenn `is_staff`; sonst `benutzer.zugewiesene_objekte`; für anonyme Nutzer leer |
| `darf_sehen(benutzer, objekt)` | Einzelprüfung für Marken und Detailseiten |
| `bereich_oder_404(benutzer, pk)` | Holt den Bereich **und** prüft die Berechtigung |
| `aufgabe_oder_404(benutzer, pk)` | Holt die Aufgabe **und** prüft die Berechtigung |

Holen und Prüfen sind bewusst zusammengelegt: Solange sie getrennte Schritte
sind, kann man das Prüfen vergessen.

Fremde Objekte ergeben **404**, nicht 403.

## Wirkung

| Stelle | Änderung |
|---|---|
| `faelligkeit.uebersicht()` | Neuer Parameter `fuer=benutzer`; filtert auf sichtbare Objekte |
| Dashboard | Nur zugewiesene Objekte |
| Bereichsseite | 404 bei fremdem Bereich |
| Abhaken (angemeldet) | 404 bei fremder Aufgabe |
| Aufgaben aus Katalog ergänzen | 404 bei fremdem Bereich |
| Freies Ereignis | 404 bei fremdem Bereich |
| Wochenmail | Je Empfänger nur dessen Objekte; ohne Zuweisung keine Mail |
| Kalender-Feed | Nur zugewiesene Objekte |
| CSV-Ausgabe | Nur Ereignisse zugewiesener Objekte |
| Abhaklink aus der Mail | Prüft die Zuweisung beim Einlösen erneut |

## Verwaltung

Im Django-Admin am **Objekt** ein Doppellisten-Feld „Betreut von", zusätzlich
am Benutzer dieselbe Beziehung von der anderen Seite. Dieselbe Zuordnung, zwei
Blickrichtungen.

## Tests

Neben je einem Test pro Stelle ein **Wächter-Test**, der die URL-Konfiguration
selbst ausliest: Für jede Route mit Objektbezug legt er ein fremdes Objekt an
und prüft, dass ein nicht zugewiesener Nutzer weder dessen Daten noch einen
Erfolgsstatus erhält.

Der Zweck ist ausdrücklich, künftige Lücken zu verhindern: Eine neue Ansicht,
die den Filter vergisst, lässt den Test umfallen, ohne dass jemand daran denken
muss.

Weitere Fälle:

- Verwaltungsberechtigte sehen unverändert alles
- Ohne Zuweisung: leeres Dashboard, keine Wochenmail, leerer Kalender, leere CSV
- Entzogene Zuweisung entwertet eine ausgegebene Abhakmarke sofort
- Ereignisse bleiben nach Entzug bestehen, samt Urheber

## Folgeänderung an SPEC.md

Abschnitt 2 wird von „alle sehen und dürfen alles, keine Rollen" zu
„Sichtbarkeit je Objekt; Verwaltungsberechtigte sehen alles". Abschnitt 7
(Funktionsumfang) bekommt die Zuweisung als Punkt. Ohne diese Nachführung
widerspricht die Spezifikation ab sofort dem Code.
