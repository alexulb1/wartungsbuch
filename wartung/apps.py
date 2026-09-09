from django.apps import AppConfig


class WartungConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wartung"

    def ready(self):
        # Registriert die Startprüfungen (siehe wartung/checks.py).
        from . import checks  # noqa: F401
