#!/bin/sh
# Nur der Webdienst wandert die Datenbank fort. Der Zeitplaner tut es
# ausdrücklich nicht: Zwei Container, die gleichzeitig migrieren, sind eine
# Fehlerquelle, die man sich sparen kann.
set -e

if [ "${ROLLE:-web}" = "web" ]; then
  echo "Datenbank wandern…"
  python manage.py migrate --noinput
fi

exec "$@"
