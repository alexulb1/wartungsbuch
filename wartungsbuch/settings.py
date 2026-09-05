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

def erlaubte_hosts(werte: dict) -> list[str]:
    """Die eigene Loopback-Adresse ist immer erlaubt.

    Die Gesundheitsprüfung des Containers ruft die Anwendung über
    http://127.0.0.1:8000/gesund auf. Fehlt die Adresse hier, antwortet Django
    mit 400, der Container gilt als krank und wird endlos neu gestartet --
    obwohl er einwandfrei arbeitet.
    """
    genannt = [t.strip() for t in (werte.get("DJANGO_ALLOWED_HOSTS") or "").split(",") if t.strip()]
    hosts = ["localhost", "127.0.0.1"]
    for host in genannt:
        if host not in hosts:
            hosts.append(host)
    return hosts


ALLOWED_HOSTS = erlaubte_hosts(os.environ)
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
    "wartung.sicherheit.SicherheitsHeaderMiddleware",
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


def _postgres(name, benutzer, passwort, host, port) -> dict:
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": benutzer,
        "PASSWORD": passwort,
        "HOST": host,
        "PORT": port,
        "CONN_MAX_AGE": 60,
    }


def _aus_url(url: str) -> dict:
    """Nur noch der Nebenweg. Eine URL zwingt dazu, Sonderzeichen im Passwort
    zu maskieren -- vergisst man das, zerreisst sie, und die Fehlermeldung
    zeigt auf eine Portnummer statt auf die eigentliche Ursache."""
    zerlegt = urlparse(url)
    if not zerlegt.scheme.startswith("postgres"):
        raise ImproperlyConfigured(f"Nicht unterstütztes Datenbankschema: {zerlegt.scheme}")
    try:
        port = zerlegt.port
    except ValueError as fehler:
        raise ImproperlyConfigured(
            "DATABASE_URL lässt sich nicht lesen — vermutlich enthält das Passwort "
            "Sonderzeichen wie ':', '/', '@' oder '?', die in einer URL maskiert "
            "werden müssten. Einfacher: statt DATABASE_URL die Einzelwerte "
            "POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER und POSTGRES_PASSWORD setzen. "
            f"({fehler})"
        ) from fehler
    return _postgres(
        name=zerlegt.path.lstrip("/"),
        benutzer=unquote(zerlegt.username or ""),
        passwort=unquote(zerlegt.password or ""),
        host=zerlegt.hostname or "",
        port=str(port or "5432"),
    )


def datenbank_konfiguration(werte: dict) -> dict:
    """Zugangsdaten aus Einzelwerten, ersatzweise aus einer URL.

    Einzelwerte sind der Regelweg: Sie kennen keine Maskierung, also kann ein
    Passwort auch beliebige Sonderzeichen enthalten (siehe test_konfiguration).
    """
    if werte.get("POSTGRES_HOST"):
        return _postgres(
            name=werte.get("POSTGRES_DB") or "wartungsbuch",
            benutzer=werte.get("POSTGRES_USER") or "wartung",
            passwort=werte.get("POSTGRES_PASSWORD") or "",
            host=werte["POSTGRES_HOST"],
            port=str(werte.get("POSTGRES_PORT") or "5432"),
        )
    if werte.get("DATABASE_URL"):
        return _aus_url(werte["DATABASE_URL"])
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "entwicklung.sqlite3"}


DATABASES = {"default": datenbank_konfiguration(os.environ)}

AUTH_USER_MODEL = "wartung.Benutzer"
LOGIN_URL = "/anmelden/"
LOGIN_REDIRECT_URL = "/"
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

# Basis fuer Links in Mails. Bewusst eine feste Angabe statt des Host-Kopfs der
# Anfrage -- sonst koennte ein gefaelschter Host Anmeldelinks umleiten.
BASIS_URL = umgebung("DJANGO_BASIS_URL", "http://localhost:8000")

# Versandtag der Wochenmail: 0 = Montag ... 6 = Sonntag, dazu die Stunde.
# Der Zeitplaner klopft stuendlich an; entschieden wird im Befehl selbst.
WOCHENMAIL_WOCHENTAG = int(umgebung("WOCHENMAIL_WOCHENTAG", "0"))
WOCHENMAIL_STUNDE = int(umgebung("WOCHENMAIL_STUNDE", "7"))

# Ablage der JSON-Sicherungen. Im Betrieb ein Verzeichnis, das die Sicherung
# des NAS mitnimmt.
SICHERUNGS_VERZEICHNIS = umgebung("DJANGO_SICHERUNGEN", str(BASE_DIR / "sicherungen"))

# --- Sicherheit (SPEC 8) -------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Das Lebenszeichen wird containerintern über HTTP abgefragt; eine Umleitung
# auf HTTPS würde die Gesundheitsprüfung scheitern lassen.
SECURE_REDIRECT_EXEMPT = [r"^gesund$"]

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
