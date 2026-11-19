# syntax=docker/dockerfile:1.7
# Pipetrace: Django + PostGIS lead service line lookup.
ARG PYTHON_IMAGE=python:3.13-slim-trixie

# ---- Build: install dependencies and the app into a virtualenv ---------------------
FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN python -m venv /opt/venv
COPY requirements/base.txt requirements/base.txt
RUN /opt/venv/bin/pip install -r requirements/base.txt
COPY pyproject.toml README.md LICENSE manage.py ./
COPY pipetrace ./pipetrace
ARG VERSION="" BUILD_NUMBER="" GIT_SHA="" BUILD_DATE=""
RUN printf '{"build_number": "%s", "commit": "%s", "build_date": "%s"}\n' \
      "$BUILD_NUMBER" "$GIT_SHA" "$BUILD_DATE" > pipetrace/_build.json \
 && /opt/venv/bin/pip install --no-deps .

# ---- Runtime ------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
ARG VERSION="" BUILD_NUMBER="" GIT_SHA="" BUILD_DATE=""
LABEL org.opencontainers.image.title="Pipetrace" \
      org.opencontainers.image.description="Publish a water system's lead service line inventory as an address search, map and resident guide." \
      org.opencontainers.image.source="https://github.com/lobojoel2003/Pipetrace" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      io.pipetrace.build-number="${BUILD_NUMBER}"

# GeoDjango needs the GDAL, GEOS and PROJ libraries.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gdal-bin \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 1000 --create-home --home-dir /app pipetrace \
 && mkdir -p /data/media /app/staticfiles \
 && chown -R pipetrace:pipetrace /data /app

COPY --from=build /opt/venv /opt/venv
COPY docker/entrypoint.sh /usr/local/bin/pipetrace-entrypoint

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=pipetrace.settings \
    PIPETRACE_STATIC_ROOT=/app/staticfiles \
    PIPETRACE_MEDIA_ROOT=/data/media \
    PIPETRACE_BASEMAP_DIR=/data/media/basemap

WORKDIR /app
USER pipetrace
RUN PIPETRACE_ALLOW_INSECURE_KEY=1 pipetrace collectstatic --noinput --verbosity 0

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

ENTRYPOINT ["pipetrace-entrypoint"]
CMD ["gunicorn", "pipetrace.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
