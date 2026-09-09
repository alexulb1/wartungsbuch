# Betrieb

Einrichtung und Pflege auf der Synology DS923+. Die fachlichen Festlegungen
stehen in [SPEC.md](SPEC.md), der Entwicklungsstand in [README.md](README.md).

## Einmalige Einrichtung

### 1. Repository und Abbild

Das Repository nach GitHub schieben. Der Arbeitsablauf
[.github/workflows/abbild.yml](.github/workflows/abbild.yml) läuft bei jedem
Push auf `main`: Er führt die Tests aus und legt danach das Abbild unter
`ghcr.io/alexulb1/wartungsbuch:latest` ab.

Das Abbild einmal auf **public** stellen (GitHub → Packages → Package settings),
dann zieht Portainer es ohne Anmeldedaten. Im Abbild stehen keine Zugangsdaten —
die kommen alle aus Umgebungsvariablen. Soll es privat bleiben, in Portainer
unter *Registries* einmalig ein GHCR-Zugangstoken hinterlegen.

### 2. Stack in Portainer

*Stacks → Add stack → Repository*, auf dieses Repository zeigen,
`docker-compose.yml` als Pfad. Unter **Environment variables** die Werte aus
[.env.beispiel](.env.beispiel) eintragen. Pflicht sind:

| Variable | Beispiel |
|---|---|
| `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | ein langer Zufallswert |
| `DJANGO_ALLOWED_HOSTS` | `wartung.example.org` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://wartung.example.org` |
| `DJANGO_BASIS_URL` | `https://wartung.example.org` |
| `ABBILD` | `ghcr.io/alexulb1/wartungsbuch:latest` |
| `SICHERUNGSPFAD` | `/volume1/docker/wartungsbuch/sicherungen` |
| `MEDIENPFAD` | `/volume1/docker/wartungsbuch/medien` |

Die beiden Pfade sind technisch nicht erzwungen — ohne sie legt Docker eigene
Volumes an, und deine NAS-Sicherung findet weder Sicherungen noch Anhänge.
Deshalb stehen sie hier bei den Pflichtangaben.

Der Stack startet drei Container:

- **datenbank** — PostgreSQL, **ohne Portfreigabe**, nur im internen Netz des
  Stacks erreichbar.
- **anwendung** — der Webdienst auf Port `8071`. Wandert beim Start die
  Datenbank fort.
- **planer** — klopft stündlich an: Wochenmail, Marken aufräumen, Sicherung.
  Wandert die Datenbank ausdrücklich **nicht** fort.

### 3. Reverse Proxy im DSM

*Systemsteuerung → Anmeldeportal → Reverse Proxy → Erstellen*

| | Quelle | Ziel |
|---|---|---|
| Protokoll | HTTPS | HTTP |
| Hostname | `wartung.example.org` | `localhost` |
| Port | 443 | 8071 |

Unter *Benutzerdefinierte Kopfzeile* die **WebSocket**-Vorlage nicht nötig, aber
`X-Forwarded-Proto` muss durchgereicht werden — DSM setzt das von sich aus.
Danach im Zertifikatsdialog das Let's-Encrypt-Zertifikat der Subdomain zuordnen.

### 4. Erstes Konto anlegen

```bash
sudo docker exec -it wartungsbuch-anwendung-1 \
  python manage.py benutzer_anlegen deine@adresse.de --name "Dein Name" --verwaltung
```

Dann den Vorlagenkatalog laden:

```bash
sudo docker exec -it wartungsbuch-anwendung-1 python manage.py katalog_laden
```

Anmelden über `https://wartung.example.org/anmelden/` — es gibt kein Passwort,
der Link kommt per Mail.

### 5. Datensicherung

Der Planer legt täglich eine JSON-Sicherung unter `/sicherungen` ab und behält
die letzten 30 Stände. Damit die NAS-Sicherung sie mitnimmt, `SICHERUNGSPFAD`
auf einen echten Pfad setzen, etwa
`/volume1/docker/wartungsbuch/sicherungen`, und diesen Ordner in Hyper Backup
aufnehmen.

**Die Sicherung besteht aus zwei Teilen.** Der JSON-Abzug enthält die Daten
samt Verweisen auf die Anhänge, der Medienordner unter `MEDIENPFAD` die Dateien
selbst. Beide gehören ins Backup — fehlt einer, führen die Verweise nach der
Wiederherstellung ins Leere. Beim Wiederherstellen zuerst den Medienordner
zurückkopieren, dann `loaddata`.

Der Sicherungsbefehl nennt bei jedem Lauf, wie viele Anhänge es gibt. Weicht
diese Zahl von der Zahl der Dateien im Medienordner ab, ist etwas
auseinandergelaufen.

JSON statt `pg_dump` ist Absicht: Der Bestand ist klein, und eine JSON-Datei
lässt sich auch dann noch lesen, wenn es diese Anwendung oder diese
Postgres-Fassung nicht mehr gibt.

Zurückspielen in eine leere Datenbank:

```bash
sudo docker exec -i wartungsbuch-anwendung-1 \
  python manage.py loaddata /sicherungen/wartungsbuch-2027-01-15.json
```

## Personen und Berechtigungen

Wer angelegt ist, sieht zunächst **nichts**. Sichtbar wird ein Objekt erst,
wenn die Person ihm zugewiesen ist — mit Ausnahme von Konten mit
Verwaltungsberechtigung, die ohnehin alles sehen.

**Konto anlegen:**

```bash
sudo docker exec wartungsbuch-anwendung-1 python manage.py benutzer_anlegen partner@example.org --name "Name"
```

Ohne `--verwaltung` bekommt das Konto keinen Zugang zum Django-Admin. Das ist
für Mitbetreuende die richtige Wahl.

**Objekt zuweisen** — im Admin auf zwei Wegen, dieselbe Zuordnung:

| Weg | Wo |
|---|---|
| Vom Objekt aus | *Objekte → Objekt öffnen → Betreut von* |
| Von der Person aus | *Benutzer → Konto öffnen → zugewiesene Objekte* |

Die Benutzerübersicht zeigt in der Spalte *Objekte*, wie viele jemand sieht;
bei Verwaltungskonten steht dort „alle".

**Eine Zuweisung gibt volle Rechte an diesem Objekt** — sehen und eintragen.
Das Objekt ist der Zaun, nicht die Tätigkeit.

**Ein Entzug wirkt sofort**, auch für Abhak-Links, die schon in einem Postfach
liegen. Bereits eingetragene Ereignisse bleiben bestehen, samt Namen: Die
Historie ist die Wahrheit und wird nicht rückwirkend umgeschrieben.

## Anhänge

Fotos, Belege und Bauteil-Unterlagen liegen als gewöhnliche Dateien unter
`MEDIENPFAD`, nicht in der Datenbank.

**Einmalig einzurichten**, vor dem ersten Hochladen:

```bash
sudo mkdir -p /volume1/docker/wartungsbuch/medien && sudo chown -R 10001:10001 /volume1/docker/wartungsbuch/medien
```

Der Container läuft als unprivilegierter Benutzer `10001`; gehört ihm der
Ordner nicht, scheitert jedes Hochladen mit „Permission denied".

Dann `MEDIENPFAD=/volume1/docker/wartungsbuch/medien` im Stack setzen und den
Ordner in Hyper Backup aufnehmen.

**Was dort liegt**, ist ohne diese Anwendung lesbar — das war der Zweck:

```
medien/haupthaus/2026-03-12_Luftfilter-wechseln_a3f9c1.jpg
       haupthaus/vorschau/a3f9c1.jpg
       haupthaus/2026-09-09_Bedienungsanleitung-Vaillant_c2cc80.pdf
       geloescht/…
```

Gelöschte Anhänge liegen 30 Tage in `geloescht/` und sind bis dahin
zurückholbar; danach räumt der Planer sie ab.

Erlaubt sind Bilder und PDF bis 25 MB. HEIC von iPhones wird angenommen, bekommt
aber keine Vorschau — *Kamera → Formate → Maximale Kompatibilität* liefert JPEG.

## Laufender Betrieb

### Aktualisieren

In Portainer beim Stack **Update the stack**, und dabei im Dialog
**„Re-pull image and redeploy" ankreuzen**. Auf dem NAS wird nichts gebaut,
die Datenbank wandert beim Start von selbst fort.

> **Das Häkchen ist keine Feinheit.** Ohne es sieht Portainer, dass bereits ein
> Container mit dem Tag `:latest` läuft, und lässt ihn stehen — obwohl
> `:latest` inzwischen auf ein neueres Abbild zeigt. Man aktualisiert dann
> scheinbar erfolgreich und schaut weiter auf den alten Stand.

Welche Fassung tatsächlich läuft, verrät die letzte Migration:

```bash
sudo docker exec wartungsbuch-anwendung-1 python manage.py showmigrations wartung | tail -2
```

### Nach dem allerersten Start

Eine leere Datenbank enthält weder Konto noch Katalog. Beides anlegen —
ohne Konto verschickt `/anmelden/` keinen Link, und zwar wortlos: Die
Anwendung antwortet absichtlich immer gleich, damit niemand ausprobieren kann,
wer ein Konto hat.

```bash
sudo docker exec wartungsbuch-anwendung-1 python manage.py benutzer_anlegen deine@adresse.de --name "Dein Name" --verwaltung
sudo docker exec wartungsbuch-anwendung-1 python manage.py katalog_laden
```

Ob die Datenbank frisch war, steht im Protokoll: `Applying
contenttypes.0001_initial... OK` erscheint nur bei einer leeren Datenbank.

### Nachsehen, ob etwas klemmt

```bash
sudo docker logs --tail 100 wartungsbuch-planer-1
sudo docker exec wartungsbuch-anwendung-1 python manage.py wochenmail --probe
curl -s http://localhost:8071/gesund
```

### Wie weit das Dashboard vorausschaut

Standardmäßig 30 Tage. Über `DASHBOARD_HORIZONT_TAGE` im Stack änderbar.
Überfälliges und noch nie Erledigtes bleibt unabhängig davon immer sichtbar;
Späteres erreichst du über „Alles anzeigen" unter der Liste.

Die Wochenmail hat ihr eigenes Fenster von 14 Tagen (SPEC 6) — das ist
Absicht: Eine Mail soll knapper sein als der Blick auf den Bildschirm.

### Wochenmail von Hand auslösen

```bash
sudo docker exec wartungsbuch-anwendung-1 python manage.py wochenmail
```

Ohne `--geplant` verschickt der Befehl sofort und übergeht die Wochensperre.

## Warum der Planer stündlich anklopft

Ein Zeitplaner, der genau montags um 7:00 auslöst, verliert die Mail, wenn der
NAS in dieser Minute gerade neu startet oder schläft. Deshalb entscheidet nicht
der Planer, sondern der Befehl selbst: Er verschickt höchstens einmal je
Kalenderwoche und **holt einen ausgefallenen Versandtag nach**. Ein stumpfer
stündlicher Aufruf genügt damit, und doppelt passiert trotzdem nichts.

Das entschärft zugleich die Annahme aus SPEC 10.2 („der NAS läuft nachts
durch"): Er muss es nicht mehr.

## Wenn etwas nicht geht

| Beobachtung | Ursache |
|---|---|
| `DisallowedHost` im Protokoll | `DJANGO_ALLOWED_HOSTS` passt nicht zur Domäne |
| Anmeldeformular meldet CSRF-Fehler | `DJANGO_CSRF_TRUSTED_ORIGINS` fehlt oder ohne `https://` |
| Links in der Mail zeigen auf `localhost` | `DJANGO_BASIS_URL` nicht gesetzt |
| Container startet nicht, „SECRET_KEY fehlt" | Absicht — ohne Schlüssel läuft nichts außerhalb des Debug-Modus |
| `Port could not be cast to integer` | Veralteter Stack, der noch `DATABASE_URL` zusammenbaut. Stack neu aus dem Repository laden — die Zugangsdaten gehen jetzt als Einzelwerte raus |
| Keine Wochenmail | `docker logs wartungsbuch-planer-1`; mit `--probe` prüfen, ob überhaupt etwas ansteht |
| Alte Fassung läuft nach dem Update weiter | „Re-pull image and redeploy" war nicht angekreuzt. Mit `showmigrations` prüfen, welche Fassung läuft |
| Hochladen endet mit Server Error 500, im Protokoll `PermissionError` | Der Medienordner gehört nicht dem Container-Benutzer: `sudo chown -R 10001:10001 /volume1/docker/wartungsbuch/medien`. Beim Start meldet sich das seit Neuestem auch von selbst als `wartung.W001` |
| `wartung.W001` im Startprotokoll | Dasselbe — der Medienordner ist nicht beschreibbar. Die Anwendung läuft trotzdem, nur Anhänge gehen nicht |
| Fotos ohne Vorschau | HEIC oder PDF — Absicht. Bei iPhones liefert *Kamera → Formate → Maximale Kompatibilität* JPEG |
| Anmeldelink kommt nicht, kein Fehler im Protokoll | Dann wurde gar kein Versand versucht — es gibt kein Konto für diese Adresse. `benutzer_anlegen` |
| SMTP prüfen, unabhängig von Konten | `docker exec wartungsbuch-anwendung-1 python manage.py sendtestemail deine@adresse.de` |
| Oberfläche ohne Gestaltung | `collectstatic` lief beim Bau nicht — Abbild neu bauen |
| Container startet endlos neu, im Protokoll `DisallowedHost: '127.0.0.1:8000'` bei `/gesund` | Behoben: Die eigene Loopback-Adresse ist jetzt immer erlaubt und von der HTTPS-Umleitung ausgenommen. Abbild neu ziehen |
| Anmeldelink kommt nicht an | Gibt es überhaupt ein Konto? `benutzer_anlegen` läuft nicht von selbst. Sonst: drei Links je Konto und Viertelstunde, danach schweigt die Anwendung |
