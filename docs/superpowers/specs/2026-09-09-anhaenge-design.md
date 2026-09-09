# Fotos und Anhänge

*Abgestimmt am 09.09.2026. Ändert SPEC.md Abschnitt 7 und 10.4.*

## Anlass

SPEC.md hält Fotos und Rechnungsanhänge bewusst aus Version 1 heraus, mit der
Zusage: „Das Datenmodell wird so gebaut, dass Anhänge und Auswertungen ohne
Umbau nachrüstbar sind." Version 1 läuft. Die Zusage wird jetzt eingelöst.

## Entscheidungen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Was soll ein Anhang leisten? | Zustandsfotos, Belege **und** Bauteil-Unterlagen | Eine Bedienungsanleitung gehört zum Bauteil, nicht zu einem Vorgang. Ohne diese zweite Andockstelle müsste man ein Schein-Ereignis erfinden — eine Lüge in der Historie |
| Wo liegen die Dateien? | Bind-Mount auf eine NAS-Freigade, `/volume1/docker/wartungsbuch/medien` | Derselbe Grund wie bei JSON statt `pg_dump`: Was in zehn Jahren lesbar sein soll, muss ohne diese Anwendung lesbar sein. Ein Ordner mit Fotos erfüllt das, ein Base64-Block in einer JSON-Datei nicht |
| Bilder verkleinern? | Original behalten, zusätzlich Vorschau erzeugen (Pillow) | Der Engpass ist das Handy über Mobilfunk, nicht der Speicherplatz. Ein verworfenes Original kommt nicht wieder — und ein Typenschild ist auf 800 px unlesbar |
| Wer liefert die Dateien aus? | Django, mit Berechtigungsprüfung | Auslieferung durch den Webserver würde die Objektberechtigungen stillschweigend aushebeln |
| Adressen | Zufällige Kennung (UUID), nicht der Dateiname | `rechnung-heizung-2026.pdf` verrät seinen Inhalt schon im Link |
| Wann anhängen? | Beim Abhaken in der App und nachträglich — **nicht** über den Link aus der Wochenmail | Ein Datei-Upload am Mail-Token wäre unangemeldeter Schreibzugriff auf den NAS-Speicher. Der Token darf genau eine Aufgabe abhaken und sonst nichts |
| Löschen | Datei wandert nach `geloescht/`, Aufräumen nach 30 Tagen | Bei etwas steuerlich Relevantem ist der Unterschied zwischen „weg" und „30 Tage zurückholbar" drei Zeilen wert |
| Grenzen | 25 MB je Datei; nur Bilder und PDF | Deckt Handyfotos und gescannte Rechnungen; je enger die Liste, desto weniger gelangt über diesen Weg auf den NAS |
| HEIC | Wird angenommen, aber ohne Vorschau | Statt einer weiteren Bildbibliothek: Datei unverändert speichern, Ersatzsymbol zeigen |

### Verworfen

| Verworfen | Grund |
|---|---|
| Dateien in der Datenbank | Postgres wächst mit jedem Foto; der JSON-Abzug bekäme Base64-Blöcke und wäre weder les- noch handhabbar |
| Docker-Volume statt Bind-Mount | Dateien lägen im Docker-Innenleben, per Dateifreigabe unerreichbar |
| Original verkleinern und verwerfen | Ein Typenschild ist auf 800 px unlesbar, und genau dann braucht man es |
| Auslieferung durch WhiteNoise/Proxy | Berechtigungen griffen nicht; Dateinamen stünden in der Adresse |
| X-Accel-Redirect | Löst ein Auslastungsproblem, das bei drei Nutzern nicht besteht, gegen dauerhafte Pflege im DSM-Proxy |
| Upload über den Abhak-Link aus der Mail | Unangemeldeter Schreibzugriff auf den Speicher |
| Zwei getrennte Anhang-Modelle | Verdoppelt Hochladen, Vorschau, Auslieferung und Berechtigung |
| Generische Beziehung (contenttypes) | Flexibilität auf Vorrat; macht jede Abfrage undurchsichtig |

## Datenmodell

Ein Modell, gebaut wie `Ereignis` — Pflicht-Bereich, optionaler Bezug:

```
Bereich ──┬─► Anhang          (Bauteil-Unterlage)
          │      │
Ereignis ─┴──────┘            (Zustandsfoto, Beleg)
```

`wartung/models/anhang.py`:

| Feld | Typ | Zweck |
|---|---|---|
| `bereich` | FK, Pflicht, CASCADE | Hieraus folgt die Berechtigung |
| `ereignis` | FK, optional, CASCADE | Gesetzt = gehört zum Vorgang; leer = gehört zum Bauteil |
| `datei` | FileField | Das Original, unverändert |
| `vorschau` | ImageField, optional | Erzeugt; fehlt bei HEIC und PDF |
| `dateiname` | CharField(255) | Der ursprüngliche Name, für den Download |
| `inhaltstyp` | CharField(100) | Zum Ausliefern |
| `groesse` | PositiveIntegerField | Bytes |
| `beschriftung` | CharField(200), leer erlaubt | „Typenschild", „Rechnung Fa. Berg" |
| `kennung` | UUIDField, eindeutig | Die Adresse |
| `hochgeladen_von` | FK Benutzer, SET_NULL | Wie bei Ereignissen |
| `hochgeladen_am` | DateTimeField | |

Bedingung in der Datenbank: Ist `ereignis` gesetzt, muss dessen `bereich` mit
`bereich` übereinstimmen — dieselbe Regel, die `Ereignis` für `aufgabe` hat.

## Ablage

```
/medien/Haupthaus/2026-03-12_Luftfilter-wechseln_a3f9c1.jpg
        Haupthaus/vorschau/a3f9c1.jpg
        Sommerhaus-Ahus/2019-06-20_Fassade-gestrichen_7b2e04.pdf
        geloescht/a3f9c1.jpg
```

Der abgelegte Name entsteht aus Datum, Tätigkeit bzw. Beschreibung und den
ersten sechs Zeichen der Kennung. Das ist der Kern der Ablage-Entscheidung: Ein
Ordner mit `2026-03-12_Luftfilter-wechseln.jpg` ist ohne Software verständlich,
ein Ordner voller UUIDs nicht. Umlaute und Sonderzeichen werden ersetzt.

Der Objektordner trägt den Namen zum Zeitpunkt des Hochladens. Wird das Objekt
später umbenannt, bleiben ältere Dateien im alten Ordner — das ist
hingenommen; die Datenbank kennt den Pfad, und der Ordnername bleibt richtig
für das, was damals galt.

Vorschau: längste Kante 1200 px, JPEG, Qualität 80.

## Auslieferung

| Adresse | Inhalt |
|---|---|
| `/anhang/<kennung>/` | Original, mit ursprünglichem Dateinamen im `Content-Disposition` |
| `/anhang/<kennung>/vorschau/` | Vorschaubild |

Beide prüfen `sichtbarkeit.darf_sehen(request.user, anhang.bereich.objekt)`.
Fremdes ergibt 404, nicht 403. Beide Routen werden im Wächter-Test
eingeordnet.

## Oberfläche

- **Abhak-Formular** und **freies Ereignis**: Dateifeld mit Mehrfachauswahl
  unter der Notiz
- **Bereichsseite**: Vorschauen am jeweiligen Ereignis in der Historie;
  darüber ein Abschnitt „Unterlagen" für die bauteilbezogenen Anhänge
- **Nachträglich anhängen** und **einzeln löschen** über die Bereichsseite
- Kein JavaScript: Klick auf die Vorschau öffnet das Original

## Sicherung

Die Sicherung zerfällt in zwei Teile:

| Teil | Wer | Wiederherstellung |
|---|---|---|
| JSON-Abzug | Planer, täglich | `loaddata` |
| Medienordner | Hyper Backup | Ordner zurückkopieren |

Der JSON-Abzug enthält die Anhang-Zeilen samt Pfaden und ist damit zugleich das
Verzeichnis zum Medienordner. Der Sicherungsbefehl nennt künftig die Zahl der
Anhänge, damit ein Auseinanderlaufen auffällt. BETRIEB.md bekommt beide Teile
im Wiederherstellungsablauf.

Der CSV-Export bekommt eine Spalte mit den Dateinamen der Anhänge.

## Betrieb

- Bind-Mount `${MEDIENPFAD:-medien}:/medien` an **beiden** Anwendungscontainern
  — der Planer braucht ihn fürs Aufräumen
- `Pillow` in `requirements.txt`
- `manage.py anhaenge_aufraeumen` entfernt `geloescht/` nach 30 Tagen; der
  Planer ruft es je Durchlauf mit auf
- Der Ordner muss dem Container-Benutzer (`uid 10001`) gehören; das kommt in
  die Fehlertabelle von BETRIEB.md

## Tests

- Berechtigung greift für Dateien: fremder Anhang ergibt 404, auch für die Vorschau
- Vorschau wird für JPEG und PNG erzeugt
- HEIC und PDF werden angenommen, ohne Vorschau
- Zu große Dateien (> 25 MB) und unerlaubte Typen werden abgewiesen
- Ein Anhang am Ereignis erbt dessen Bereich; ein widersprüchlicher Bereich wird beanstandet
- Gelöschte Anhänge landen in `geloescht/`, die Datenbankzeile verschwindet
- `anhaenge_aufraeumen` entfernt nach 30 Tagen, Jüngeres bleibt
- Der ursprüngliche Dateiname steht im Download, nicht der abgelegte
- Die zwei neuen Routen sind im Wächter-Test eingeordnet

## Folgeänderung an SPEC.md

Abschnitt 7 verliert „Fotos und Rechnungsanhänge" aus der Liste des bewusst
Weggelassenen und bekommt sie in den Funktionsumfang. Abschnitt 10.4 wird um
den Medienordner ergänzt. Abschnitt 11 bekommt die hier verworfenen
Alternativen.
