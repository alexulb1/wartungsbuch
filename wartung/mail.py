"""Mailversand.

Zwei Grundsaetze:

1. Jede Mail geht in der Sprache ihres Empfaengers raus (SPEC 2).
2. Links werden aus einer festen Basisadresse gebaut, nie aus dem Host-Kopf der
   Anfrage. Sonst koennte ein gefaelschter Host-Kopf Anmeldelinks auf einen
   fremden Server zeigen lassen.
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import translation


def adresse(pfad: str) -> str:
    return f"{settings.BASIS_URL.rstrip('/')}{pfad}"


def senden(benutzer, betreff_vorlage: str, text_vorlage: str, zusammenhang: dict) -> None:
    with translation.override(benutzer.sprache):
        betreff = render_to_string(betreff_vorlage, zusammenhang).strip()
        text = render_to_string(text_vorlage, zusammenhang)
    EmailMessage(subject=betreff, body=text, to=[benutzer.email]).send()
