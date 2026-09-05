"""Sprachwahl aus dem Benutzerprofil (SPEC 2, SPEC 3).

Die Oberflaeche richtet sich nicht nach dem Browser, sondern nach dem, was im
Profil hinterlegt ist: Meldet sich B an, ist alles schwedisch -- unabhaengig
davon, an welchem Geraet.
"""

from django.utils import translation


class SpracheAusProfilMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        benutzer = getattr(request, "user", None)
        if benutzer is not None and benutzer.is_authenticated and benutzer.sprache:
            translation.activate(benutzer.sprache)
            request.LANGUAGE_CODE = translation.get_language()
        return self.get_response(request)
