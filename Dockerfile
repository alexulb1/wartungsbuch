# Wartungsbuch — Abbild für den Betrieb auf der Synology (SPEC 9).
#
# Bewusst einstufig und ohne Kunstgriffe: Ein Abbild, das in zehn Jahren noch
# nachvollziehbar ist, wiegt hier mehr als ein paar eingesparte Megabyte.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# gettext übersetzt die Sprachdateien beim Bau — so kann kein veralteter
# Übersetzungsstand ins Abbild geraten.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gettext \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN DJANGO_DEBUG=1 python manage.py compilemessages --ignore .venv \
 && DJANGO_DEBUG=0 DJANGO_SECRET_KEY=nur-fuer-den-bau python manage.py collectstatic --noinput

# Unprivilegiert laufen (SPEC 8).
RUN useradd --system --create-home --uid 10001 wartung \
 && mkdir -p /sicherungen /medien \
 && chown -R wartung:wartung /app /sicherungen /medien
USER wartung

EXPOSE 8000

ENTRYPOINT ["/app/einstieg.sh"]
CMD ["gunicorn", "wartungsbuch.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-"]
