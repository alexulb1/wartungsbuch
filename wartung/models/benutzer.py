"""Benutzerkonten.

Die Anwendung meldet ueber Magic Link an (SPEC 2), Passwoerter werden nicht
verwendet. Neue Konten bekommen deshalb ein unbrauchbares Passwort gesetzt.
Der Django-Admin ist ueber dieselbe Sitzung erreichbar: Wer per Magic Link
angemeldet und als Personal markiert ist, kommt ohne Passwort hinein.
"""

import secrets

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from .basis import Sprache


def neuer_kalenderschluessel() -> str:
    """Langlebiger Schluessel fuer das Kalender-Abo (SPEC 7).

    Anders als eine Zugangsmarke wird er nicht verbraucht -- ein Abo ruft die
    Adresse dauernd ab. Er gibt nur Termine preis, keine Anmeldung."""
    return secrets.token_urlsafe(24)


class BenutzerManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, name="", sprache=Sprache.DEUTSCH, **extra):
        if not email:
            raise ValueError("Ein Benutzer braucht eine E-Mail-Adresse.")
        benutzer = self.model(
            email=self.normalize_email(email), name=name, sprache=sprache, **extra
        )
        benutzer.set_unusable_password()
        benutzer.save(using=self._db)
        return benutzer

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        benutzer = self.create_user(email, **extra)
        if password:
            # Nur fuer den Notfallzugang gedacht; der Regelweg ist der Magic Link.
            benutzer.set_password(password)
            benutzer.save(using=self._db)
        return benutzer


class Benutzer(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("E-Mail"), unique=True)
    name = models.CharField(_("Name"), max_length=120, blank=True)
    sprache = models.CharField(
        _("Sprache"),
        max_length=2,
        choices=Sprache.choices,
        default=Sprache.DEUTSCH,
        help_text=_("Bestimmt Oberfläche und Sprache der Wochenmail."),
    )
    is_active = models.BooleanField(_("aktiv"), default=True)
    is_staff = models.BooleanField(_("Zugang zur Verwaltung"), default=False)
    kalender_schluessel = models.CharField(
        _("Kalenderschlüssel"), max_length=43, unique=True, default=neuer_kalenderschluessel
    )
    angelegt_am = models.DateTimeField(_("angelegt am"), auto_now_add=True)

    objects = BenutzerManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("Benutzer")
        verbose_name_plural = _("Benutzer")
        ordering = ["email"]

    def __str__(self) -> str:
        return self.name or self.email

    def get_short_name(self) -> str:
        return self.name or self.email.split("@")[0]
