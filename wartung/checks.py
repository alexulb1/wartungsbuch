"""Prüfungen, die beim Start laufen.

Django führt sie bei jedem ``manage.py``-Aufruf aus, also auch beim ``migrate``
im Einstiegsskript des Containers. Damit steht ein falsch eingerichteter
Medienordner im Protokoll, sobald der Container hochkommt -- und nicht erst
beim ersten Foto als Server Error 500, aus dem niemand die Ursache erraten kann.

Bewusst eine Warnung und kein Fehler: Ein nicht beschreibbarer Medienordner
macht das Hochladen unmöglich, aber nicht die Anwendung. Ein Fehler würde den
Container gar nicht erst starten lassen -- das wäre schlimmer als das Problem.
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.checks import Warning, register

#: Der unprivilegierte Benutzer, unter dem der Container läuft (siehe Dockerfile).
CONTAINER_BENUTZER = 10001


@register()
def medienordner_beschreibbar(app_configs, **kwargs):
    ordner = Path(settings.MEDIA_ROOT)

    try:
        ordner.mkdir(parents=True, exist_ok=True)
    except OSError as fehler:
        return [_warnung(ordner, fehler)]

    if not os.access(ordner, os.W_OK | os.X_OK):
        return [_warnung(ordner, "kein Schreibrecht")]

    return []


def _warnung(ordner: Path, ursache) -> Warning:
    return Warning(
        f"Der Medienordner {ordner} ist nicht beschreibbar ({ursache}). "
        "Anhänge lassen sich nicht hochladen.",
        hint=(
            f"Auf dem NAS gehört der Ordner dem Container-Benutzer: "
            f"sudo chown -R {CONTAINER_BENUTZER}:{CONTAINER_BENUTZER} <MEDIENPFAD>"
        ),
        id="wartung.W001",
    )
