"""Erzeugt ein verkleinertes Vorschaubild.

Das Original bleibt unangetastet. Der Engpass ist das Handy über Mobilfunk,
nicht der Speicherplatz -- und ein Typenschild ist auf 800 Pixel unlesbar,
weshalb das Original nie verworfen wird.
"""

from io import BytesIO

from django.core.files.base import ContentFile

#: Längste Kante der Vorschau. Ergibt je nach Motiv 150-250 kB statt 3-5 MB.
VORSCHAU_KANTE = 1200
QUALITAET = 80


def vorschau_erzeugen(datei) -> ContentFile | None:
    """Gibt None zurück, wenn sich kein Bild erzeugen lässt.

    Das ist der Regelfall für PDF und für HEIC, das Pillow ohne Zusatzpaket
    nicht öffnet. Die Datei bleibt trotzdem erhalten; in der Oberfläche steht
    dann ein Ersatzsymbol.
    """
    from PIL import Image, UnidentifiedImageError

    datei.seek(0)
    try:
        with Image.open(datei) as bild:
            bild.load()
            if bild.mode not in ("RGB", "L"):
                bild = bild.convert("RGB")
            bild.thumbnail((VORSCHAU_KANTE, VORSCHAU_KANTE), Image.LANCZOS)
            puffer = BytesIO()
            bild.save(puffer, format="JPEG", quality=QUALITAET, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    finally:
        datei.seek(0)

    # Der Name ist Pflicht: Django ruft beim Speichern file.save(file.name, …),
    # und eine ContentFile ohne Namen bricht dort ab. Den tatsächlichen Pfad
    # bestimmt ohnehin vorschaupfad().
    return ContentFile(puffer.getvalue(), name="vorschau.jpg")
