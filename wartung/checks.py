"""Prüfungen, die beim Start laufen.

Django führt sie bei jedem ``manage.py``-Aufruf aus, also auch beim ``migrate``
im Einstiegsskript des Containers. Damit steht ein falsch eingerichteter
Ablageordner im Protokoll, sobald der Container hochkommt -- und nicht erst
beim ersten Foto als Server Error 500, aus dem niemand die Ursache erraten kann.

Bewusst Warnungen und keine Fehler: Ein nicht beschreibbarer Ordner macht das
Hochladen oder die Sicherung unmöglich, aber nicht die Anwendung. Ein Fehler
würde den Container gar nicht erst starten lassen -- das wäre schlimmer als das
Problem, das er meldet.
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.checks import Warning, register

#: Benutzer und Gruppe, unter denen der Container läuft (siehe Dockerfile).
#: Die Gruppennummer wird von useradd vergeben und ist nicht gleich der
#: Benutzernummer -- ein "chown 10001:10001" geht deshalb ins Leere, sobald
#: Gruppenrechte eine Rolle spielen.
CONTAINER_BENUTZER = 10001
CONTAINER_GRUPPE = 999


def _pruefe(ordner: Path, was: str, kennung: str):
    try:
        ordner.mkdir(parents=True, exist_ok=True)
    except OSError as fehler:
        return _warnung(ordner, was, kennung, str(fehler))

    if not os.access(ordner, os.W_OK | os.X_OK):
        # Häufigster Fall in der Praxis: Der Besitzer stimmt, aber der
        # Zugriffsmodus verbietet allen alles.
        modus = oct(ordner.stat().st_mode & 0o777)
        return _warnung(ordner, was, kennung, f"kein Schreibrecht, Zugriffsmodus {modus}")

    return None


def _warnung(ordner: Path, was: str, kennung: str, ursache: str) -> Warning:
    return Warning(
        f"Der Ordner für {was} ({ordner}) ist nicht beschreibbar: {ursache}.",
        hint=(
            "Auf dem NAS braucht der Ordner Besitzer und Zugriffsmodus: "
            f"sudo chown -R {CONTAINER_BENUTZER}:{CONTAINER_GRUPPE} <PFAD> "
            "&& sudo chmod -R 750 <PFAD>. "
            "Prüfen mit: docker exec <container> ls -ldn " + str(ordner)
        ),
        id=kennung,
    )


@register()
def ablageordner_beschreibbar(app_configs, **kwargs):
    meldungen = [
        _pruefe(Path(settings.MEDIA_ROOT), "Anhänge", "wartung.W001"),
        _pruefe(Path(settings.SICHERUNGS_VERZEICHNIS), "Sicherungen", "wartung.W002"),
    ]
    return [meldung for meldung in meldungen if meldung is not None]
