# Wartungsbuch

Wartungshistorie und Erinnerungsplan für mehrere Wohnobjekte.
Die abgestimmten Anforderungen stehen in [SPEC.md](SPEC.md) — bei Zweifeln
gilt die Spezifikation, nicht der Code.

## Stand

**Schritt 3 von 5 abgeschlossen:** Gerüst, Datenmodell, Fälligkeit, Oberfläche.

| Schritt | Inhalt | Stand |
|--------:|--------|-------|
| 1 | Gerüst, Datenmodell, Admin, Katalog | fertig |
| 2 | Fälligkeitsberechnung (beide Intervallmodi, Ruhezeit) | fertig |
| 3 | Oberfläche und Mehrsprachigkeit | fertig |
| 4 | Wochenmail, Token, ICS, CSV-Export | offen |
| 5 | Container, Portainer-Stack, Inbetriebnahme | offen |

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

### Zugang bis Schritt 4

Die Anwendung kennt keine Passwörter — die Anmeldung läuft später über einen
Magic Link (Schritt 4). Bis dahin gibt es keinen Weg in den Admin. Übergangs­weise
lässt sich für ein Verwaltungskonto ein Passwort setzen:

```bash
.venv/bin/python manage.py changepassword ich@example.org
```

Sobald der Magic Link steht, ist dieses Passwort mit
`manage.py shell -c "..."` wieder zu entwerten — ein Konto mit Passwort ist
eine Hintertür an der eigentlichen Anmeldung vorbei.

## Befehle

| Befehl | Zweck |
|--------|-------|
| `manage.py katalog_laden` | Vorlagenkatalog anlegen/aktualisieren (wiederholbar) |
| `manage.py benutzer_anlegen <email>` | Konto für die Anmeldung per Magic Link |
| `manage.py test wartung` | Testlauf |
| `manage.py makemessages -l en -l sv --no-location --no-wrap -i ".venv/*"` | Neue Texte in die Sprachdateien übernehmen |
| `manage.py compilemessages --ignore .venv` | Übersetzungen übersetzen |

## Aufbau

```
wartung/models/basis.py      Sprachen, Intervalleinheiten, Übersetzungs-Mixin
wartung/models/benutzer.py   Konten (ohne Passwort, Magic Link)
wartung/models/katalog.py    Objekttypen, Bereichstypen, Tätigkeiten (dreisprachig)
wartung/models/bestand.py    Objekt → Bereich → Aufgabe
wartung/models/ereignis.py   Ereignis — die einzige Wahrheit
wartung/katalogdaten.py      Inhalt des Vorlagenkatalogs
wartung/faelligkeit.py       Fälligkeitsberechnung — der Kern
wartung/views.py             Dashboard, Historie, Abhaken, Vorlagen, Profil
wartung/forms.py             Formulare
wartung/sicherheit.py        Content-Security-Policy
wartung/templates/wartung/   Vorlagen der Oberfläche
locale/{en,sv}/              Übersetzungen (Deutsch ist die Quellsprache)
```

## Grundsätze

- **Die Fälligkeit wird berechnet, nie gespeichert.** Sie ergibt sich aus dem
  jüngsten Ereignis plus Intervall. Es gibt keinen Status, der veralten kann.
- **Katalogdaten werden ausgewählt, Freitext bleibt Freitext.** Nur so ist
  Mehrsprachigkeit möglich und nur so sind Auswertungen über Objekte hinweg
  überhaupt beantwortbar.
- **Wenige Abhängigkeiten.** Die Anwendung soll in zehn Jahren noch laufen.
- **Der Stichtag wird hineingereicht, nie aus der Systemuhr gelesen.** Das macht
  jede Berechnung prüfbar und erlaubt Vorschauen auf andere Termine.
- **Der Kalendermodus zählt in Jahren.** Ein Monatsintervall und ein fester
  Monat widersprechen einander; die Datenbank weist die Kombination zurück.
