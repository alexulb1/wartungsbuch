"""Legt ein Benutzerkonto an -- ohne Passwort (SPEC 2).

    python manage.py benutzer_anlegen a@example.org --name "Alex" --sprache de --verwaltung
"""

from django.core.management.base import BaseCommand, CommandError

from wartung.models import Benutzer, Sprache


class Command(BaseCommand):
    help = "Legt ein Benutzerkonto fuer die Anmeldung per Magic Link an."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--name", default="")
        parser.add_argument("--sprache", default=Sprache.DEUTSCH, choices=[s for s, _ in Sprache.choices])
        parser.add_argument(
            "--verwaltung",
            action="store_true",
            help="Gibt Zugang zum Django-Admin (is_staff und is_superuser).",
        )

    def handle(self, *args, **optionen):
        email = optionen["email"].strip().lower()
        if Benutzer.objects.filter(email__iexact=email).exists():
            raise CommandError(f"Es gibt bereits ein Konto fuer {email}.")
        benutzer = Benutzer.objects.create_user(
            email=email,
            name=optionen["name"],
            sprache=optionen["sprache"],
            is_staff=optionen["verwaltung"],
            is_superuser=optionen["verwaltung"],
        )
        self.stdout.write(
            self.style.SUCCESS(f"Konto angelegt: {benutzer.email} (Sprache: {benutzer.sprache})")
        )
