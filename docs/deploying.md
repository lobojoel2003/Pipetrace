# Deploying Pipetrace

Pipetrace runs as one web container next to a PostgreSQL + PostGIS database. A
small water system can also skip the server entirely and publish a
[static export](static-hosting.md).

## Option 1: Docker Compose (recommended)

You need a Linux machine (a small cloud VM is plenty) with Docker installed.

1. Copy [`docker-compose.yml`](../docker-compose.yml) to the machine.
2. Create a `.env` file next to it. Use long random values:

   ```dotenv
   POSTGRES_PASSWORD=a-long-random-database-password
   PIPETRACE_SECRET_KEY=another-long-random-string-at-least-50-characters-long
   PIPETRACE_ALLOWED_HOSTS=leadlines.yourtown.gov
   PIPETRACE_CSRF_TRUSTED_ORIGINS=https://leadlines.yourtown.gov
   PIPETRACE_ADMIN_USER=admin
   PIPETRACE_ADMIN_PASSWORD=a-strong-password-you-change-after-first-login
   PIPETRACE_LOAD_DEMO=0
   PIPETRACE_SECURE=1
   ```

   Generate random strings with `openssl rand -base64 48`.

3. Start it:

   ```bash
   docker compose up -d
   ```

4. Put HTTPS in front of port 8000 with any reverse proxy (Caddy, nginx, a cloud load
   balancer). With Caddy the whole configuration is:

   ```caddyfile
   leadlines.yourtown.gov {
       reverse_proxy localhost:8000
   }
   ```

5. Sign in at `https://leadlines.yourtown.gov/staff/`, open **Settings** and fill in
   your utility's name, phone, programs and default city/state, then
   [import your inventory](importing.md).

The container runs database migrations on start and creates the admin user from
`PIPETRACE_ADMIN_USER`/`PIPETRACE_ADMIN_PASSWORD` if it doesn't exist yet.

### Images and versions

Images are published to GitHub Container Registry for `linux/amd64` and
`linux/arm64`:

| Tag | What it is |
| --- | --- |
| `ghcr.io/lobojoel2003/pipetrace:1.0.0` | an exact release |
| `ghcr.io/lobojoel2003/pipetrace:1.0` / `:1` | the newest release in that line |
| `ghcr.io/lobojoel2003/pipetrace:latest` | the newest stable release |
| `ghcr.io/lobojoel2003/pipetrace:build-57` | the release from CI build 57 |
| `ghcr.io/lobojoel2003/pipetrace:edge` | the current `main` branch (not for production) |

Pin a version in production: `PIPETRACE_IMAGE=ghcr.io/lobojoel2003/pipetrace:1.0`.
The running version and build number are shown in the page footer and at `/healthz`.

### Upgrading

```bash
docker compose pull && docker compose up -d
```

Migrations run automatically. Read the [changelog](../CHANGELOG.md) first.

### Backups

Everything lives in two Docker volumes: `db` (the database) and `media` (uploaded
spreadsheets, residents' photos and the basemap). Back up the database daily:

```bash
docker compose exec -T db pg_dump -U pipetrace -Fc pipetrace > pipetrace-$(date +%F).dump
```

and copy the `media` volume (`docker run --rm -v pipetrace_media:/data -v "$PWD":/backup
alpine tar czf /backup/media.tgz -C /data .`).

## Option 2: Without Docker

Requirements: Python 3.12+, PostgreSQL 14+ with PostGIS 3, GDAL (`gdal-bin` on
Debian/Ubuntu).

```bash
python -m venv /opt/pipetrace && . /opt/pipetrace/bin/activate
pip install pipetrace-1.0.0-py3-none-any.whl   # from the GitHub release
export DATABASE_URL=postgis://pipetrace:password@localhost:5432/pipetrace
export PIPETRACE_SECRET_KEY=... PIPETRACE_ALLOWED_HOSTS=leadlines.yourtown.gov
pipetrace migrate
pipetrace collectstatic --noinput
pipetrace createsuperuser
gunicorn pipetrace.wsgi --bind 127.0.0.1:8000 --workers 3
```

The `pipetrace` command is the same as Django's `manage.py`. Run it under systemd
(or any process manager) and put a reverse proxy with HTTPS in front.

## Scheduled jobs

Nothing is required. Optionally run `pipetrace geocode` from cron after you import
by command line, and back up the database.

## Health checks

`GET /healthz` returns `200` with `{"status": "ok", "database": "ok", "version": ...}`
when the app and database are up, `503` otherwise. The Docker image uses it as its
`HEALTHCHECK`.
