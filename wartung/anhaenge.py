"""Legt hochgeladene Dateien als Anhänge ab.

An einer Stelle gebündelt, weil drei Ansichten dasselbe tun: Abhaken, freies
Ereignis und nachträgliches Anhängen.
"""

from .models import Anhang
from .vorschau import vorschau_erzeugen


def anhaenge_speichern(
    dateien, bereich, benutzer, ereignis=None, beschriftung=""
) -> list[Anhang]:
    """Die Dateien sind zu diesem Zeitpunkt bereits geprüft (siehe Formular).

    Die Beschriftung gehört hier hinein und nicht in einen zweiten Schritt:
    Sie geht in den abgelegten Dateinamen ein, und der steht beim Speichern
    fest.
    """
    angelegt = []
    for datei in dateien:
        anhang = Anhang(
            bereich=bereich,
            ereignis=ereignis,
            dateiname=datei.name[:255],
            inhaltstyp=(getattr(datei, "content_type", "") or "")[:100],
            groesse=datei.size,
            beschriftung=beschriftung[:200],
            hochgeladen_von=benutzer if getattr(benutzer, "is_authenticated", False) else None,
        )
        anhang.datei = datei
        bild = vorschau_erzeugen(datei)
        if bild is not None:
            anhang.vorschau = bild
        anhang.save()
        angelegt.append(anhang)
    return angelegt
