"""Waechter ueber die Sprachdateien (SPEC 3).

Anlass: msgmerge markiert aehnliche Eintraege als "fuzzy" und raet eine
Uebersetzung. msgfmt uebergeht fuzzy-Eintraege beim Uebersetzen -- die Anwendung
zeigt dann stillschweigend Deutsch, obwohl die .po-Datei gefuellt aussieht.
Genau so stand "Erledigt:" auf Deutsch in der schwedischen Wochenmail.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

SPRACHEN = ["en", "sv"]


def eintraege(sprache):
    pfad = Path(settings.BASE_DIR) / "locale" / sprache / "LC_MESSAGES" / "django.po"
    text = pfad.read_text()
    bloecke = text.split("\n\n")
    for block in bloecke:
        treffer = re.search(r'^msgid "(.*)"', block, re.MULTILINE)
        if not treffer or treffer.group(1) == "":
            continue
        yield block, treffer.group(1)


class SprachdateienTest(TestCase):
    def test_keine_fuzzy_eintraege(self):
        for sprache in SPRACHEN:
            for block, msgid in eintraege(sprache):
                with self.subTest(sprache=sprache, msgid=msgid):
                    self.assertNotIn(
                        "#, fuzzy",
                        block,
                        "fuzzy-Einträge werden beim Übersetzen übergangen "
                        "und erscheinen still auf Deutsch",
                    )

    def test_keine_leeren_uebersetzungen(self):
        for sprache in SPRACHEN:
            for block, msgid in eintraege(sprache):
                with self.subTest(sprache=sprache, msgid=msgid):
                    self.assertNotRegex(block, r'^msgstr(\[\d\])? ""$', )
