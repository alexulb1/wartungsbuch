"""Content-Security-Policy (SPEC 8).

Von Hand statt per Zusatzpaket: Die Anwendung laedt nichts aus fremden Quellen,
und ihr einziges Skript (die Absendesperre) liegt als eigene Datei vor -- kein
eingebettetes JavaScript. Deshalb genuegen wenige Zeilen.
"""

RICHTLINIE = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data:",
        "style-src 'self'",
        "script-src 'self'",
        "form-action 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
    ]
)

# Der Django-Admin bringt eigene eingebettete Stile und Skripte mit und laesst
# sich nicht streng absichern. Er ist nur fuer angemeldetes Personal erreichbar.
RICHTLINIE_ADMIN = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline'",
        "script-src 'self' 'unsafe-inline'",
        "form-action 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
    ]
)


class SicherheitsHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        antwort = self.get_response(request)
        antwort.setdefault(
            "Content-Security-Policy",
            RICHTLINIE_ADMIN if request.path.startswith("/admin/") else RICHTLINIE,
        )
        antwort.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return antwort
