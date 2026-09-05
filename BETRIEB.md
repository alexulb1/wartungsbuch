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

JSON statt `pg_dump` ist Absicht: Der Bestand ist klein, und eine JSON-Datei
lässt sich auch dann noch lesen, wenn es diese Anwendung oder diese
Postgres-Fassung nicht mehr gibt.

Zurückspielen in eine leere Datenbank:

```bash
sudo docker exec -i wartungsbuch-anwendung-1 \
  python manage.py loaddata /sicherungen/wartungsbuch-2027-01-15.json
```

## Laufender Betrieb

### Aktualisieren

In Portainer beim Stack **Update the stack** mit *Re-pull image* — mehr nicht.
Auf dem NAS wird nichts gebaut. Die Datenbank wandert beim Start von selbst fort.

### Nachsehen, ob etwas klemmt

```bash
sudo docker logs --tail 100 wartungsbuch-planer-1
sudo docker exec wartungsbuch-anwendung-1 python manage.py wochenmail --probe
curl -s http://localhost:8071/gesund
```

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
| Oberfläche ohne Gestaltung | `collectstatic` lief beim Bau nicht — Abbild neu bauen |
| Container startet endlos neu, im Protokoll `DisallowedHost: '127.0.0.1:8000'` bei `/gesund` | Behoben: Die eigene Loopback-Adresse ist jetzt immer erlaubt und von der HTTPS-Umleitung ausgenommen. Abbild neu ziehen |
| Anmeldelink kommt nicht an | Gibt es überhaupt ein Konto? `benutzer_anlegen` läuft nicht von selbst. Sonst: drei Links je Konto und Viertelstunde, danach schweigt die Anwendung |
