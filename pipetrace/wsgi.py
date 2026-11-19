"""WSGI entry point (used by gunicorn: ``gunicorn pipetrace.wsgi``)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pipetrace.settings")

application = get_wsgi_application()
