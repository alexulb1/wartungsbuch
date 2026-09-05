"""Konfiguration.

Alles Umgebungsabhaengige kommt aus Umgebungsvariablen -- im Image stehen
keine Zugangsdaten (SPEC 8). Ohne gesetzte DATABASE_URL faellt die Anwendung
auf eine lokale SQLite-Datei zurueck, damit die Entwicklung ohne laufenden
Postgres-Container moeglich bleibt.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


def umgebung(name: str, standard: str | None = None, *, pflicht: bool = False) -> str:
    wert = os.environ.get(name, standard)
    if pflicht and not wert:
        raise ImproperlyConfigured(f"Umgebungsvariable {name} fehlt.")
    return wert or ""


def schalter(name: str, standard: bool = False) -> bool:
    return umgebung(name, "1" if standard else "0").strip().lower() in {"1", "true", "yes", "ja"}


def liste(name: str) -> list[str]:
    return [t.strip() for t in umgebung(name).split(",") if t.strip()]


DEBUG = schalter("DJANGO_DEBUG", False)

SECRET_KEY = umgebung(
    "DJANGO_SECRET_KEY",
    "unsicherer-entwicklungsschluessel" if DEBUG else None,
    pflicht=not DEBUG,
)

ALLOWED_HOSTS = liste("DJANGO_ALLOWED_HOSTS") or (["localhost", "127.0.0.1"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = liste("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "wartung",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "wartung.middleware.SpracheAusProfilMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "wartungsbuch.urls"
WSGI_APPLICATION = "wartungsbuch.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


def datenbank_konfiguration(url: str) -> dict:
    if not url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "entwicklung.sqlite3"}
    z = urlparse(url)
    if not z.scheme.startswith("postgres"):
        raise ImproperlyConfigured(f"Nicht unterstuetztes Datenbankschema: {z.scheme}")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": z.path.lstrip("/"),
        "USER": unquote(z.username or ""),
        "PASSWORD": unquote(z.password or ""),
        "HOST": z.hostname or "",
        "PORT": str(z.port or ""),
        "CONN_MAX_AGE": 60,
    }


DATABASES = {"default": datenbank_konfiguration(umgebung("DATABASE_URL"))}

AUTH_USER_MODEL = "wartung.Benutzer"
AUTH_PASSWORD_VALIDATORS = []  # Es werden keine Passwoerter vergeben (SPEC 2).
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Sprache und Zeit (SPEC 3) -------------------------------------------
LANGUAGE_CODE = "de"
LANGUAGES = [("de", _("Deutsch")), ("en", _("Englisch")), ("sv", _("Schwedisch"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = umgebung("DJANGO_TIME_ZONE", "Europe/Berlin")

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Der Manifest-Speicher setzt ein vorheriges collectstatic voraus und ist
# deshalb nur im Produktionsbetrieb sinnvoll.
STATICFILES_BACKEND = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": STATICFILES_BACKEND},
}

# --- Mailversand (SPEC 6) ------------------------------------------------
EMAIL_BACKEND = umgebung(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = umgebung("EMAIL_HOST")
EMAIL_PORT = int(umgebung("EMAIL_PORT", "587"))
EMAIL_HOST_USER = umgebung("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = umgebung("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = schalter("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = umgebung("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "wartungsbuch@localhost")

# --- Sicherheit (SPEC 8) -------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    # Die Anwendung laeuft hinter dem DSM-Reverse-Proxy, der TLS terminiert.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = schalter("DJANGO_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(umgebung("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = schalter("DJANGO_HSTS_SUBDOMAINS", False)
    SECURE_HSTS_PRELOAD = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"einfach": {"format": "{levelname} {asctime} {name} {message}", "style": "{"}},
    "handlers": {"konsole": {"class": "logging.StreamHandler", "formatter": "einfach"}},
    "root": {"handlers": ["konsole"], "level": umgebung("DJANGO_LOG_LEVEL", "INFO")},
}
