# Wartungsbuch — Spezifikation

*Ergebnis der Anforderungsklärung vom 05.09.2026. Status: abgestimmt.*

## 1. Zweck

Festhalten, **was wann gemacht wurde** (Historie), und rechtzeitig erinnern,
**was ansteht** (Plan). Beides aus einer Datenquelle, nicht aus zwei.

Bestand: zwei Objekte — ein Einfamilienhaus und ein Sommerhaus. Wärmepumpe,
Klimageräte, Fassaden. Selbst bewohnt, keine Mieter.

## 2. Nutzer und Zugang

- Der Eigentümer und wenige Vertraute. Alle sehen und dürfen alles, keine Rollen.
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
| Freitext      | Objektname „Sommerhaus Åhus", Firmenname, Notiz                        | bleibt wie eingegeben |

**Konsequenz fürs Datenmodell:** Objekttypen, Bereichstypen und Tätigkeiten
werden **aus Katalogen ausgewählt statt frei getippt**. Das ist die
Voraussetzung für Mehrsprachigkeit und macht zugleich Auswertungen über beide
Objekte hinweg möglich. Freitext bleibt für Eigennamen und Notizen — also für
das, was man ohnehin nicht übersetzt.

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

## 7. Funktionsumfang Version 1

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

### Bewusst nicht in Version 1

Fotos und Rechnungsanhänge · Kostenauswertungen · Push-Benachrichtigungen ·
Offline-Betrieb · Mieter- und Rollenverwaltung · Tabellen-Import.

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
