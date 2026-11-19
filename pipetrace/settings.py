"""Django settings for Pipetrace.

Everything a deployment needs to change is read from environment variables, so
the same code runs in development, in Docker and on a plain VM. See
``docs/configuration.md`` for the full list.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = env(name, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    value = env(name)
    return int(value) if value is not None else default


DEBUG = env_bool("PIPETRACE_DEBUG", False)

SECRET_KEY = env("PIPETRACE_SECRET_KEY") or env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG or env_bool("PIPETRACE_ALLOW_INSECURE_KEY"):
        SECRET_KEY = "pipetrace-insecure-development-key-change-me"
    else:
        raise ImproperlyConfigured(
            "Set PIPETRACE_SECRET_KEY to a long random string "
            "(or PIPETRACE_DEBUG=1 for local development)."
        )

ALLOWED_HOSTS = env_list("PIPETRACE_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
# Container health checks call http://127.0.0.1:8000/healthz whatever the public host is.
ALLOWED_HOSTS += [h for h in ("127.0.0.1", "localhost") if h not in ALLOWED_HOSTS]
CSRF_TRUSTED_ORIGINS = env_list("PIPETRACE_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
    "django.contrib.humanize",
    "pipetrace.core",
    "pipetrace.inventory",
    "pipetrace.residents",
    "pipetrace.staff",
    "pipetrace.export",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "pipetrace.core.middleware.SecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pipetrace.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pipetrace.core.context_processors.pipetrace",
            ],
        },
    },
]

WSGI_APPLICATION = "pipetrace.wsgi.application"

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgis://pipetrace:pipetrace@localhost:5432/pipetrace"),
        conn_max_age=env_int("PIPETRACE_DB_CONN_MAX_AGE", 60),
        conn_health_checks=True,
    )
}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "staff:login"
LOGIN_REDIRECT_URL = "staff:dashboard"
LOGOUT_REDIRECT_URL = "staff:login"

# --- Internationalisation -------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", _("English")),
    ("es", _("Spanish")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = env("PIPETRACE_TIME_ZONE", "America/Chicago")
USE_I18N = True
USE_TZ = True

# --- Static and uploaded files --------------------------------------------
STATIC_URL = env("PIPETRACE_STATIC_URL", "/static/")
STATIC_ROOT = Path(env("PIPETRACE_STATIC_ROOT", str(PROJECT_DIR / "staticfiles")))
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = env("PIPETRACE_MEDIA_URL", "/media/")
MEDIA_ROOT = Path(env("PIPETRACE_MEDIA_ROOT", str(PROJECT_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
WHITENOISE_KEEP_ONLY_HASHED_FILES = False
WHITENOISE_MIMETYPES = {".mjs": "text/javascript", ".pbf": "application/x-protobuf"}

# Folder holding a Protomaps .pmtiles basemap, served at /basemap/ (see docs/basemap.md).
PIPETRACE_BASEMAP_DIR = Path(env("PIPETRACE_BASEMAP_DIR", str(MEDIA_ROOT / "basemap")))

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

# --- Security --------------------------------------------------------------
SECURE = env_bool("PIPETRACE_SECURE", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if SECURE else None
SECURE_SSL_REDIRECT = SECURE and env_bool("PIPETRACE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = SECURE
CSRF_COOKIE_SECURE = SECURE
SECURE_HSTS_SECONDS = env_int("PIPETRACE_HSTS_SECONDS", 31536000 if SECURE else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE
# Preloading is a long-term commitment for the whole domain; opt in explicitly.
SECURE_HSTS_PRELOAD = env_bool("PIPETRACE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SILENCED_SYSTEM_CHECKS = [
    # GDAL < 3.9 cannot sandbox file/network access while parsing spatial references.
    # Pipetrace never hands untrusted files to GDAL (spreadsheets are read by openpyxl and
    # points are built from numbers), so the warning does not apply.
    "gis.W001",
]
if not SECURE_HSTS_PRELOAD:
    SILENCED_SYSTEM_CHECKS += ["security.W021"]
if not SECURE:
    # Plain-HTTP development and internal deployments; set PIPETRACE_SECURE=1 behind HTTPS.
    SILENCED_SYSTEM_CHECKS += ["security.W004", "security.W008", "security.W012", "security.W016"]

# --- Email -------------------------------------------------------------------
EMAIL_HOST = env("PIPETRACE_EMAIL_HOST")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = env_int("PIPETRACE_EMAIL_PORT", 587)
    EMAIL_HOST_USER = env("PIPETRACE_EMAIL_USER", "")
    EMAIL_HOST_PASSWORD = env("PIPETRACE_EMAIL_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("PIPETRACE_EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("PIPETRACE_FROM_EMAIL", "pipetrace@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- Caching -----------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "pipetrace",
    }
}

# --- Logging -----------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("PIPETRACE_LOG_LEVEL", "INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# --- Pipetrace -----------------------------------------------------------------
PIPETRACE = {
    # Geocoder for addresses without coordinates: "census", "pelias" or "none".
    "GEOCODER": env("PIPETRACE_GEOCODER", "census"),
    "CENSUS_URL": env("PIPETRACE_CENSUS_URL", "https://geocoding.geo.census.gov/geocoder"),
    "CENSUS_BENCHMARK": env("PIPETRACE_CENSUS_BENCHMARK", "Public_AR_Current"),
    "PELIAS_URL": env("PIPETRACE_PELIAS_URL", "http://localhost:4000"),
    "PELIAS_API_KEY": env("PIPETRACE_PELIAS_API_KEY", ""),
    "GEOCODE_BATCH_SIZE": env_int("PIPETRACE_GEOCODE_BATCH_SIZE", 250),
    "GEOCODE_TIMEOUT": env_int("PIPETRACE_GEOCODE_TIMEOUT", 120),
    # Addresses to email when a resident sends a request or a photo.
    "NOTIFY_EMAILS": env_list("PIPETRACE_NOTIFY_EMAILS"),
    # Submissions allowed per visitor per hour (simple abuse protection).
    "SUBMISSIONS_PER_HOUR": env_int("PIPETRACE_SUBMISSIONS_PER_HOUR", 10),
    # Largest photo a resident may upload, in megabytes.
    "MAX_PHOTO_MB": env_int("PIPETRACE_MAX_PHOTO_MB", 15),
    # Largest inventory spreadsheet staff may upload, in megabytes.
    "MAX_IMPORT_MB": env_int("PIPETRACE_MAX_IMPORT_MB", 50),
    # Extra origins allowed in the Content-Security-Policy connect-src, for a
    # basemap hosted on another domain (e.g. a PMTiles file on a CDN).
    "CSP_CONNECT_SRC": env_list("PIPETRACE_CSP_CONNECT_SRC"),
    # Origins allowed to POST forms to /api/submit/ from a static export ("*" = any).
    "STATIC_SITE_ORIGINS": env_list("PIPETRACE_STATIC_SITE_ORIGINS", "*"),
}
