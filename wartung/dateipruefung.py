"""Prüft hochgeladene Dateien auf Größe und Typ.

Bewusst eng: Erlaubt sind Bilder und PDF. Je kleiner die Liste, desto weniger
gelangt über diesen Weg auf den Speicher.
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from .models.anhang import ERLAUBTE_TYPEN, HOECHSTGROESSE

#: Endungen, die wir auch dann akzeptieren, wenn der Browser keinen brauchbaren
#: Inhaltstyp mitschickt (manche senden application/octet-stream).
ERLAUBTE_ENDUNGEN = set(ERLAUBTE_TYPEN.values()) | {".jpeg"}


def pruefe_datei(datei) -> None:
    if datei.size > HOECHSTGROESSE:
        grenze = HOECHSTGROESSE // (1024 * 1024)
        raise ValidationError(
            _("„%(name)s“ ist zu groß. Höchstens %(grenze)s MB je Datei.")
            % {"name": datei.name, "grenze": grenze}
        )

    typ = (getattr(datei, "content_type", "") or "").lower()
    endung = Path(datei.name).suffix.lower()
    if typ in ERLAUBTE_TYPEN or endung in ERLAUBTE_ENDUNGEN:
        return

    raise ValidationError(
        _("„%(name)s“ ist kein erlaubter Dateityp. Erlaubt sind Bilder und PDF.")
        % {"name": datei.name}
    )
