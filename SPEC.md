# Wartungsbuch — Spezifikation

*Ergebnis der Anforderungsklärung vom 05.09.2026. Status: abgestimmt.*

## 1. Zweck

Festhalten, **was wann gemacht wurde** (Historie), und rechtzeitig erinnern,
**was ansteht** (Plan). Beides aus einer Datenquelle, nicht aus zwei.

Bestand: zwei Objekte — ein Einfamilienhaus und ein Sommerhaus. Wärmepumpe,
Klimageräte, Fassaden. Selbst bewohnt, keine Mieter.

## 2. Nutzer und Zugang

- Der Eigentümer und wenige Vertraute.
- **Sichtbarkeit je Objekt:** Personen werden einzelnen Objekten zugewiesen und
  sehen nur diese samt Bereichen, Aufgaben und Ereignissen. Ohne Zuweisung ist
  nichts sichtbar. Wer Verwaltungsberechtigung hat, sieht alles.
- Eine Zuweisung gibt volle Rechte an diesem Objekt — sehen und eintragen. Das
  Objekt ist der Zaun, nicht die Tätigkeit.
- **Magic Link** als Anmeldung: E-Mail eingeben, Anmeldelink kommt, kein Passwort.
  Zugelassene Adressen sind fest hinterlegt, keine Selbstregistrierung.
- Responsive Web-Anwendung für Handy und Schreibtisch. **Online-only**, kein
  Offline-Betrieb.
- Jede Person hat ein Profil mit Sprachwahl. Oberfläche **und Wochenmail**
  erscheinen in der im Profil hinterlegten Sprache.

## 3. Mehrsprachigkeit — Deutsch / Englisch / Schwedisch

Drei Textsorten, unterschiedlich behandelt:

| Sorte         | Beispiel                                                              | Übersetzung        |
|---------------|-----------------------------------------------------------------------|--------------------|
| Oberfläche    | Knöpfe, Spaltenüberschriften, Mailtexte                                | dreisprachig       |
| Katalogdaten  | Objekttyp „Haus", Bereichstyp „Wärmepumpe", Tätigkeit „Luftfilter wechseln" | dreisprachig gepflegt |
| Bereichszusatz | „Ost", „EG" — unterscheidet gleichartige Bereiche                     | dreisprachig eingebbar, Rückfall auf Deutsch |
| Freitext      | Objektname „Sommerhaus Åhus", Firmenname, Notiz                        | bleibt wie eingegeben |

**Konsequenz fürs Datenmodell:** Objekttypen, Bereichstypen und Tätigkeiten
werden **aus Katalogen ausgewählt statt frei getippt**. Das ist die
Voraussetzung für Mehrsprachigkeit und macht zugleich Auswertungen über beide
Objekte hinweg möglich. Freitext bleibt für Eigennamen und Notizen — also für
das, was man ohnehin nicht übersetzt. Der unterscheidende Zusatz am Bereich
ist der Zwischenfall: selbst getippt, aber übersetzbar, weil er zusammen mit
dem Bereichstyp gelesen wird („Facade East", nicht „Facade Ost").

Ausgangssprache ist Deutsch; Englisch und Schwedisch werden übersetzt. Die
schwedische Fassung der Fachbegriffe wird vom Eigentümer gegengelesen.

## 4. Datenmodell

```
Objekt  ──►  Bereich  ──►  Ereignis
(Typ aus      (Typ aus       (12.03.2026, Filter gewechselt,
 Katalog)      Katalog)       45 EUR, Fa. Müller, "RAL 7016")
                  │
                  └──►  Aufgabe (Tätigkeit aus Katalog + Intervall)
```

- **Das Ereignis ist die einzige Wahrheit.** Felder: Datum, Bereich, Tätigkeit
  bzw. Beschreibung, Kosten, ausführende Person/Firma, Notiz.
- Erledigungsdatum ist **frei wählbar**, vorbelegt mit „heute". Dokumentation
  hinkt der Arbeit nach; das darf die Fälligkeit nicht verschieben.
- Ein Ereignis **kann** auf eine Aufgabe verweisen, muss aber nicht. Einmaliges
  („Bad renoviert 2019") braucht keine Pseudo-Aufgabe.
- **Fälligkeit wird immer berechnet, nie gespeichert.** Es gibt keinen
  Fälligkeitszustand, der veralten oder von der Realität abweichen könnte.
  Nachgetragene Ereignisse korrigieren die Fälligkeit rückwirkend.
- Der Urheber eines Ereignisses ergibt sich automatisch aus Login bzw.
  Mail-Token — auch beim Abhaken ohne Anmeldung.

## 5. Intervalle

Pro Aufgabe umschaltbar:

- **Relativ zur letzten Erledigung** (Standard) — „30 Tage nach dem
  tatsächlichen Filterwechsel".
- **Fester Kalenderrhythmus** — „jedes Jahr im Mai", für Saisonales und
  Termingebundenes. Ersetzt ein separates Saisonfenster.

## 6. Erinnerung

- **Eine Sammelmail pro Woche** mit **14-Tage-Vorschau**, gruppiert nach Objekt,
  damit sich Fahrten bündeln lassen. Ist nichts fällig, kommt keine Mail.
- Jede Aufgabe in der Mail trägt einen **Ein-Klick-Link** auf eine schlanke
  Bestätigungsseite: Datum korrigieren, Kosten und Notiz eintragen, speichern.
  Kein Login nötig.
- **Kein „Später erinnern"-Knopf.** Er führte einen gespeicherten Zustand ein,
  den das Modell sonst nirgends kennt — und die Mail kommt in sieben Tagen wieder.
- **Ruhezeit pro Objekt:** Das Sommerhaus erscheint außerhalb seiner aktiven
  Monate nicht in der Wochenmail. Fälligkeiten laufen im Hintergrund weiter und
  sind in der App jederzeit sichtbar; zum Saisonstart kommt eine gebündelte
  **Ankunftsliste**.

Begründung des Ruhezeit-Mechanismus: Eine Erinnerung, auf die man nicht handeln
kann, entwertet alle anderen mit.

## 7. Funktionsumfang

### Version 1

- Objekte, Bereiche, Aufgaben und Ereignisse anlegen und pflegen
- Dashboard: was ist fällig, was ist überfällig
- Historie je Bereich („wann wurde die Nordseite zuletzt gestrichen")
- **Dreisprachiger Vorlagenkatalog**: Bereichstyp wählen (Wärmepumpe,
  Klimagerät, Fassade …) → typische Tätigkeiten mit üblichen Intervallen zur
  Auswahl. Der Katalog transportiert Fachwissen, nicht nur gesparte Tipparbeit:
  Er beantwortet „woran hätte ich denken müssen".
- Wochenmail und Abhak-Seite
- **ICS-Kalender-Feed** zum Abonnieren
- **CSV-Export** aller Ereignisse

### Danach ergänzt

Version 1 lief, bevor diese Punkte entstanden. Jeder hat einen eigenen Entwurf
unter `docs/superpowers/specs/`, wo auch die verworfenen Alternativen stehen.

- **Objektbezogene Berechtigungen**: Personen werden Objekten zugewiesen und
  sehen nur diese. Ohne Zuweisung ist nichts sichtbar; Verwaltungsberechtigte
  sehen alles. Ändert die ursprüngliche Festlegung „alle sehen alles" aus
  Abschnitt 2
- **Anhänge**: Fotos und Belege am Ereignis, Unterlagen am Bereich. Das Original
  bleibt unverändert, dazu ein Vorschaubild. Bis 25 MB, Bilder und PDF.
  Gelöschtes bleibt 30 Tage zurückholbar
- **Dashboard-Horizont**: Standardmäßig 30 Tage, über
  `DASHBOARD_HORIZONT_TAGE` änderbar. Überfälliges bleibt unabhängig davon
  sichtbar, Späteres ist über „Alles anzeigen" erreichbar. Eine Aufgabe, die
  2031 fällig wird, gehört nicht unter „Was ansteht"
- **„Ausgeführt von" ist vorbelegt** mit dem Namen dessen, der abhakt —
  überschreibbar, wenn eine Firma gearbeitet hat
- **Aufgaben stilllegen und löschen** in der Anwendung, nicht nur in der
  Verwaltung. *Stilllegen* nimmt die Aufgabe aus Dashboard, Wochenmail und
  Kalender, lässt aber alle Einstellungen stehen; stillgelegte bleiben auf der
  Bereichsseite sichtbar, sonst wären sie nicht zurückzuholen. *Löschen* fragt
  vorher nach und nennt dabei, wie viele Ereignisse stehenbleiben — in einer
  Aufgabe steckt eine Festlegung, die man nicht in zehn Sekunden
  wiederherstellt. **Die Ereignisse bleiben in beiden Fällen**
- **Wartungsnachweis je Objekt**: alles, was an einem Objekt geschah, nach
  Bereich gegliedert und innerhalb chronologisch, mit Kopfdaten und
  Gesamtkosten, wahlweise auf einen Zeitraum eingegrenzt. Zum Weitergeben
  gedacht — deshalb nach Bereich: Wer das Dokument bekommt, fragt nach dem
  Dach, nicht nach dem März. Anhänge stehen mit Namen darin, nicht als Bild
- **Jahresvorschau**: die nächsten zwölf Monate nach Monat gruppiert,
  Überfälliges als eigener Block oben
- **Beide als Druckseite, nicht als erzeugtes PDF.** Der Browser macht daraus
  die Datei; das Ergebnis ist dasselbe, ohne eine Bibliothek auf zehn Jahre
- **Einzelne Ereignisse löschen** in der Historie und aus dem Nachweis heraus
  (dort nicht mitgedruckt; danach zurück in denselben Nachweis — als Rückweg
  gilt nur der Nachweis desselben Objekts, sonst wäre es eine offene
  Weiterleitung). Berechtigt ist, wer das Objekt sieht. Mit Rückfrage. Sie nennt die
  Zahl der mitgehenden Anhänge und **rechnet die Folge für die Fälligkeit vorher
  aus**: Wer die jüngste Erledigung löscht, verschiebt den nächsten Termin
  rückwärts. Ohne diesen Hinweis wundert man sich über eine Wochenmail, die man
  nicht erwartet hat — die Kehrseite davon, dass Fälligkeit berechnet und nie
  gespeichert wird
- **Sperre gegen doppeltes Absenden**, in zwei Schichten. Im Browser nimmt ein
  abgeschicktes Formular keinen zweiten Klick an. Auf dem Server trägt jedes
  angezeigte Formular eine Einmal-Kennung, die die Datenbank nur einmal zulässt —
  das hält ohne JavaScript und bei sich überholenden Anfragen. Doppelt ist nur,
  was mit derselben Kennung, vom selben Urheber und mit demselben Inhalt kommt:
  Wer mit „Zurück" bewusst einen weiteren Eintrag erfasst, wird nicht verschluckt

- **Bereichsbezeichnung dreisprachig.** Der Zusatz, der gleichartige Bereiche
  unterscheidet, steht in allen drei Sprachen. Der deutsche Text bleibt der
  führende: Er ist Pflicht, er entscheidet über Eindeutigkeit je Objekt und
  über die Sortierung, und er springt ein, wo eine Übersetzung fehlt

### Bewusst nicht in Version 1

Kostenauswertungen · Push-Benachrichtigungen ·
Offline-Betrieb · Rollen unterhalb der Objektzuweisung (etwa nur-lesend) ·
Tabellen-Import.

Kosten werden erfasst, nur nicht ausgewertet — der CSV-Export überbrückt das.
Das Datenmodell wird so gebaut, dass Anhänge und Auswertungen ohne Umbau
nachrüstbar sind.

## 8. Sicherheit

Fester Bestandteil, nicht optional:

- Django mit produktionstauglichen Voreinstellungen: CSRF-Schutz, HSTS, strikte
  Content-Security-Policy, Cookies nur über HTTPS und ohne JavaScript-Zugriff,
  kein Debug-Modus
- **Zwei getrennte Token-Klassen.** Der Anmelde-Link erzeugt eine Sitzung, der
  Abhak-Link aus der Wochenmail **nicht**. Wer einen Abhak-Link abfängt, kann
  genau eine Aufgabe abhaken und sonst nichts. Beide einmalig verwendbar und
  kurzlebig.
- Ratenbegrenzung auf der Anmeldeseite
- Postgres ohne Portfreigabe, nur im internen Container-Netz erreichbar
- Zugangsdaten ausschließlich als Umgebungsvariablen, nie im Image
- Container laufen als unprivilegierter Benutzer, nicht als root
- Protokollierung fehlgeschlagener Anmeldeversuche

Zustandsändernde Links wirken nie allein durch Aufruf, sondern erst nach
Bestätigung — Mailprogramme und Virenscanner rufen Links vorab ab.

## 9. Technik und Betrieb

- **Django** (Python), serverseitig gerendert, wenig JavaScript. Der
  Django-Admin übernimmt die Pflegeoberfläche.
- **PostgreSQL** im eigenen Container.
- **Synology DS923+ — x86-64** (AMD Ryzen R1600), nicht ARM.
- Erreichbar über eine Subdomain der bestehenden Domäne, hinter dem bereits
  eingerichteten DSM-Reverse-Proxy mit Let's Encrypt.
- **Code auf GitHub**, Image automatisch nach **GHCR** gebaut. Auslieferung als
  **Compose-YAML für Portainer**, die nur das fertige Image zieht. Update =
  „Image neu ziehen, neu starten", kein Build auf dem NAS.
- Wochenmail als Zeitplanaufgabe, Versand über SMTP des Mailanbieters.

Auswahlkriterium für den Stack war nicht Entwicklungsgeschwindigkeit, sondern
Langlebigkeit: Bei Intervallen im Zehnjahresbereich muss die Anwendung 2036
noch laufen und die Daten von 2026 enthalten.

## 10. Annahmen

1. Ereignisse lassen sich nachträglich korrigieren und löschen.
2. Der NAS läuft nachts durch — sonst fällt die Wochenmail aus. *Zu prüfen.*
3. Eine Subdomain lässt sich im DSM-Reverse-Proxy anlegen.
4. Datensicherung über das bestehende NAS-Backup; zusätzlich wird ein
   automatischer Datenbank-Abzug eingerichtet, den das Backup mitnimmt.
5. Git-Repository privat, Container-Image öffentlich (im Image stehen keine
   Zugangsdaten). Soll auch das Image privat sein, sind in Portainer einmalig
   Registry-Zugangsdaten zu hinterlegen.
6. Bei Altbeständen mit unscharfem Datum wird der Monatserste eingetragen und
   „ca." in die Notiz geschrieben. Kein eigenes Feature.

## 11. Verworfene Alternativen und ihre Begründung

| Verworfen | Grund |
|---|---|
| Push-Benachrichtigungen | Viel Mechanik (Service Worker, VAPID, iOS-Sonderweg) für wenig Mehrwert gegenüber E-Mail |
| Tägliche Einzelmails | Zerstückelte Meldungen lassen keine Fahrten bündeln und werden weggeklickt |
| Getrennte Historie und Wartungsplan | Driften auseinander; niemand weiß dann, welcher Seite zu trauen ist |
| Abhaken per reinem Link-Aufruf | Mailprogramme und Scanner rufen Links vorab ab und haken von selbst ab |
| „Später erinnern" | Zusätzlicher gespeicherter Zustand; die Wochenmail wiederholt sich ohnehin |
| Offline-Betrieb | Konfliktauflösung bei gemeinsamer Datenbasis ist der aufwendigste Teil der App und löst ein Problem, das ein frei wählbares Datum bereits löst |
| Passwörter | Bei monatlicher Nutzung wird der Reset-Weg zum Hauptanmeldeweg; Magic Link macht ihn zum einzigen |
| SQLite | Wunsch nach eigenem Datenbank-Container; Konsistenz zum bestehenden Betriebsmodell |
| Node/TypeScript | Kürzeste Halbwertszeit der Alternativen; hunderte Abhängigkeiten altern schlecht |
| Go | Wartungsärmer, aber jedes Formular von Hand — der Django-Admin liefert die halbe App |
| Dreifache Namensfelder (DE/EN/SV) | Verdreifacht die Eingabearbeit an der ohnehin größten Hürde; Kataloge lösen es besser |
| Vorgelagerte Zugangssperre | Zerstört das Ein-Klick-Abhaken, ohne das reale Risiko (abgefangener Link) zu senken |
| Tabellen-Import | Mehr Arbeit als der Vorlagenkatalog und hilft nur ein einziges Mal |
| Rolle je Zuweisung (lesen / mitarbeiten) | Kein tatsächlicher Nur-Lesen-Fall; verdoppelt jede Zuweisungsentscheidung |
| Eigenes Kennzeichen „sieht alle Objekte" | Bei wenigen Objekten identisch mit „allen Objekten zugewiesen" |
| Berechtigungsbibliothek (django-guardian) | Eine Abhängigkeit auf zehn Jahre für eine Regel in dreißig Zeilen |
| Anhänge in der Datenbank | Postgres wächst mit jedem Foto; der JSON-Abzug bekäme Base64-Blöcke und wäre weder les- noch handhabbar |
| Original verkleinern und verwerfen | Ein Typenschild ist auf 800 px unlesbar, und genau dann braucht man es |
| Anhänge über den Webserver ausliefern | Die Objektberechtigungen griffen nicht; Dateinamen stünden in der Adresse |
| Upload über den Abhak-Link aus der Mail | Unangemeldeter Schreibzugriff auf den Speicher |
| Aufgaben mit einem Klick löschen, ohne Rückfrage | In einer Aufgabe steckt Intervall, Modus und Termin — anders als bei einem Anhang stellt man das nicht in zehn Sekunden wieder her |
| Stillgelegte Aufgaben ganz ausblenden | Dann wären sie nirgends mehr erreichbar und ließen sich nie zurückholen |
| PDF-Bibliothek für den Nachweis (WeasyPrint, ReportLab) | Der Browser liefert dieselbe Datei. WeasyPrint zöge Systembibliotheken nach, die bei Aktualisierungen erfahrungsgemäß brechen; ReportLab hieße, das Layout von Hand statt in CSS zu bauen |
| Fotos im Nachweis abdrucken | Bläht das Dokument auf, und wer es in die Hand bekommt, kann sie ohnehin nicht öffnen — der Dateiname sagt ihm, dass es sie gibt |
| Auswertung nach Handwerksfirma | „Ausgeführt von" ist Freitext; beim vierten Mal steht dort „Berg GmbH" statt „Fa. Berg" und nichts gruppiert sich. Bräuchte erst einen Katalog |
| Kostenauswertung nach Jahren | Weiterhin zurückgestellt: Sie beantwortet erst mit drei, vier Jahren Daten etwas |
| Bereiche und Objekte samt Historie löschbar machen | Ein versehentlicher Klick soll nicht zehn Jahre Dokumentation mitreißen |
