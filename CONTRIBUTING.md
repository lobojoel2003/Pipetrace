# Contributing to Pipetrace

Thanks for helping water systems tell residents what their pipes are made of.

## Development setup

You need Python 3.12+, PostgreSQL with PostGIS, and GDAL.

```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgis gdal-bin gettext
sudo -u postgres createuser --superuser pipetrace --pwprompt   # password: pipetrace
sudo -u postgres createdb -O pipetrace pipetrace

python -m venv .venv && . .venv/bin/activate
pip install -r requirements/dev.txt && pip install --no-deps -e .
export PIPETRACE_DEBUG=1
python manage.py migrate
python manage.py load_demo          # fictional Millbrook data
python manage.py createsuperuser
python manage.py runserver
```

Or run everything in Docker: `docker compose up --build`.

## Checks

```bash
ruff check . && ruff format --check .
pytest                                  # unit and integration tests (needs PostGIS)
python manage.py export_static site --base-url /Pipetrace/
PIPETRACE_E2E_SITE=site pytest -m e2e   # browser tests of the static site
```

## Translations

Every resident-facing string is in English and Spanish. After changing text:

```bash
cd pipetrace
python ../manage.py makemessages -l es --no-location --no-obsolete -i "static/*"
# edit locale/es/LC_MESSAGES/django.po
python ../manage.py compilemessages -l es
```

`tests/test_i18n.py` fails if any string is untranslated.

## Front end

There is no JavaScript build step. Code in `pipetrace/static/pipetrace/js/` is plain ES
modules; map libraries are vendored in `pipetrace/static/pipetrace/vendor/` (see
`VENDORED.md` there). Keep pages usable without JavaScript where possible.

## Releases

1. `python scripts/release.py X.Y.Z` bumps the version and dates the changelog.
2. Commit and push to `main`, then either push the tag `vX.Y.Z` or open
   **Actions → Release → Run workflow** and enter `X.Y.Z` (the workflow creates the tag).
3. The Release workflow runs the tests, builds the wheel, the demo site and the
   container images, and publishes a GitHub Release named
   "Pipetrace X.Y.Z (build N)", where N is the CI build number.
