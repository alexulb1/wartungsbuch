# Wartungsbuch

Wartungshistorie und Erinnerungsplan für mehrere Wohnobjekte.
Die abgestimmten Anforderungen stehen in [SPEC.md](SPEC.md) — bei Zweifeln
gilt die Spezifikation, nicht der Code.

## Stand

**Im Betrieb.** Einrichtung und Pflege: [BETRIEB.md](BETRIEB.md). Was man
eintragen kann: [BEISPIELE.md](BEISPIELE.md).

261 Tests · 8 Migrationen · 5 Abhängigkeiten (Django, psycopg, WhiteNoise,
Gunicorn, Pillow)

**Version 1** — in fünf Schritten gebaut:

| | Inhalt |
|--:|--------|
| 1 | Gerüst, Datenmodell, Admin, Vorlagenkatalog |
| 2 | Fälligkeitsberechnung (beide Intervallmodi, Ruhezeit) |
| 3 | Oberfläche und Mehrsprachigkeit (de/en/sv) |
| 4 | Wochenmail, Zugangsmarken, ICS-Feed, CSV-Ausgabe |
| 5 | Container, Portainer-Stack, Inbetriebnahme |

**Danach ergänzt**, jeweils mit Entwurf und Plan unter `docs/superpowers/`:

| Ergänzung | Entwurf |
|-----------|---------|
| Objektbezogene Berechtigungen | [2026-09-05](docs/superpowers/specs/2026-09-05-objektberechtigungen-design.md) |
| Fotos und Anhänge | [2026-09-09](docs/superpowers/specs/2026-09-09-anhaenge-design.md) |
| Dashboard-Horizont (30 Tage) | — |
| Vorbelegung von „ausgeführt von" | — |
| Aufgaben stilllegen und löschen | — |

## Entwicklung

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DJANGO_DEBUG=1
.venv/bin/python manage.py migrate
.venv/bin/python manage.py katalog_laden
.venv/bin/python manage.py benutzer_anlegen ich@example.org --name "Alex" --verwaltung
.venv/bin/python manage.py runserver
```

Ohne `DATABASE_URL` läuft die Anwendung auf einer lokalen SQLite-Datei; im
Betrieb kommt PostgreSQL aus dem eigenen Container. Ohne `DJANGO_DEBUG=1`
verlangt die Anwendung einen `DJANGO_SECRET_KEY` und startet sonst nicht —
das ist Absicht.

Vorlage für die Umgebungsvariablen: [.env.beispiel](.env.beispiel)

### Anmelden

Es gibt keine Passwörter. Auf `/anmelden/` die Adresse eintragen, der
Anmeldelink kommt per E-Mail; im Entwicklungsmodus landet er in der Ausgabe
des Servers. Der Django-Admin ist über dieselbe Sitzung erreichbar.

Sollte für den Notfall doch einmal ein Passwort gesetzt worden sein, gehört es
wieder entwertet — ein Konto mit Passwort ist eine Hintertür an der
eigentlichen Anmeldung vorbei.

## Befehle

| Befehl | Zweck |
|--------|-------|
| `manage.py katalog_laden` | Vorlagenkatalog anlegen/aktualisieren (wiederholbar) |
| `manage.py benutzer_anlegen <email>` | Konto für die Anmeldung per Magic Link |
| `manage.py wochenmail` | Sammelmail verschicken (wöchentlich einplanen) |
| `manage.py wochenmail --probe --stichtag 2027-01-15` | Vorschau, ohne zu verschicken |
| `manage.py marken_aufraeumen` | Verbrauchte Zugangsmarken löschen (wöchentlich) |
| `manage.py anhaenge_aufraeumen` | Papierkorb der Anhänge leeren (der Planer tut es stündlich) |
| `manage.py planer` | Zeitplaner für den Dauerbetrieb (stündlich) |
| `manage.py sicherung --taeglich` | JSON-Sicherung schreiben |
| `manage.py test wartung` | Testlauf |
| `manage.py makemessages -l en -l sv --no-location --no-wrap -i ".venv/*"` | Neue Texte in die Sprachdateien übernehmen |
| `manage.py compilemessages --ignore .venv` | Übersetzungen übersetzen |

## Aufbau

**Datenmodell**

```
wartung/models/basis.py      Sprachen, Intervalleinheiten, Übersetzungs-Mixin
wartung/models/benutzer.py   Konten (ohne Passwort) und Objektzuweisung
wartung/models/katalog.py    Objekttypen, Bereichstypen, Tätigkeiten (dreisprachig)
wartung/models/bestand.py    Objekt → Bereich → Aufgabe
wartung/models/ereignis.py   Ereignis — die einzige Wahrheit
wartung/models/anhang.py     Anhänge — Ablagepfad und Papierkorb
wartung/models/zugang.py     Zugangsmarken — Magic Link und Ein-Klick-Abhaken
wartung/models/versand.py    Protokoll der verschickten Wochenmails
wartung/katalogdaten.py      Inhalt des Vorlagenkatalogs
```

**Fachlogik**

```
wartung/faelligkeit.py       Fälligkeitsberechnung — der Kern
wartung/sichtbarkeit.py      Wer sieht welche Objekte
wartung/versandplan.py       Wann die Wochenmail rausgeht
wartung/dateipruefung.py     Größe und Typ hochgeladener Dateien
wartung/vorschau.py          Vorschaubilder
wartung/anhaenge.py          Hochgeladene Dateien ablegen
wartung/kalender.py          ICS-Feed
wartung/mail.py              Mailversand in der Sprache des Empfängers
```

**Oberfläche und Rahmen**

```
wartung/views.py             Dashboard, Historie, Abhaken, Anhänge, Aufgaben, Profil
wartung/forms.py             Formulare
wartung/urls.py              Routen
wartung/admin.py             Pflegeoberfläche
wartung/middleware.py        Sprache aus dem Benutzerprofil
wartung/sicherheit.py        Content-Security-Policy
wartung/checks.py            Startprüfungen (Ablageordner beschreibbar?)
wartung/templates/wartung/   Vorlagen der Oberfläche
locale/{en,sv}/              Übersetzungen (Deutsch ist die Quellsprache)
```

**Betrieb**

```
wartung/management/commands/ Zeitplaner, Wochenmail, Sicherung, Aufräumen
Dockerfile                   Abbild für den Betrieb
docker-compose.yml           Stack für Portainer
.github/workflows/           Tests und Abbildbau bei jedem Push
docs/superpowers/            Entwürfe und Umsetzungspläne der Erweiterungen
```

## Grundsätze

- **Die Fälligkeit wird berechnet, nie gespeichert.** Sie ergibt sich aus dem
  jüngsten Ereignis plus Intervall. Es gibt keinen Status, der veralten kann.
- **Katalogdaten werden ausgewählt, Freitext bleibt Freitext.** Nur so ist
  Mehrsprachigkeit möglich und nur so sind Auswertungen über Objekte hinweg
  überhaupt beantwortbar.
- **Wenige Abhängigkeiten.** Die Anwendung soll in zehn Jahren noch laufen.
- **Zwei Klassen von Zugangsmarken.** Der Anmeldelink erzeugt eine Sitzung, der
  Abhaklink nicht. Ein abgefangener Abhaklink hakt genau eine Aufgabe ab.
- **Gespeichert wird nur der Hash einer Marke.** Eine Datenbanksicherung enthält
  keine benutzbaren Links.
- **Links in Mails entstehen aus `DJANGO_BASIS_URL`,** nie aus dem Host-Kopf der
  Anfrage.
- **Sichtbarkeit wird an einer Stelle entschieden.** Alle datenliefernden Pfade
  gehen über `sichtbarkeit.py`; ein Wächter-Test geht die Routen durch und
  besteht darauf, dass jede eingeordnet ist.
- **Was ausgeblendet wird, bleibt sichtbar ausgeblendet.** Das Dashboard zeigt
  30 Tage, nennt aber die Zahl der späteren Aufgaben — sonst fragt man sich,
  ob man sie je angelegt hat.
- **Anhänge liegen als Dateien, nicht in der Datenbank.** Ein Ordner mit
  `2026-03-12_Luftfilter-wechseln.jpg` ist 2036 ohne Software verständlich.
  Der Preis: Die Sicherung besteht aus zwei Teilen.
- **Der Zeitplaner klopft nur an, er entscheidet nicht.** Die Befehle sind
  idempotent und holen einen ausgefallenen Termin nach. Ein Neustart zur
  falschen Minute kostet deshalb keine Wochenmail.
- **Der Stichtag wird hineingereicht, nie aus der Systemuhr gelesen.** Das macht
  jede Berechnung prüfbar und erlaubt Vorschauen auf andere Termine.
- **Der Kalendermodus zählt in Jahren.** Ein Monatsintervall und ein fester
  Monat widersprechen einander; die Datenbank weist die Kombination zurück.
- **Falsche Einrichtung meldet sich beim Start.** Ein fehlender
  `DJANGO_SECRET_KEY` verhindert den Start, ein nicht beschreibbarer
  Medienordner erzeugt eine Warnung — nicht erst beim ersten Foto ein 500er,
  aus dem niemand die Ursache erraten kann.
- **Fremdes ergibt 404, nie 403.** Eine Berechtigungsmeldung bestätigt, dass es
  das Objekt gibt.
- **Was nur einmal wirken darf, hängt nie an einem GET.** Abhaken und Löschen
  verlangen ein POST — Mailprogramme und Virenscanner rufen Links vorab ab.
- **Die Historie überlebt das Löschen.** Eine gelöschte Aufgabe nimmt ihre
  Ereignisse nicht mit, und ein Bereich mit Ereignissen lässt sich gar nicht
  erst löschen. Was geschehen ist, bleibt.
