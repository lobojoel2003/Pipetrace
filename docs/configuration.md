# Configuration

There are two kinds of settings:

* **Site settings** that change what residents see (your utility's name, phone,
  programs, the replacement deadline, the basemap). Edit them in the staff area under
  **Settings**. They take effect immediately.
* **Environment variables** for the server itself, read at start-up.

## Site settings

| Setting | Used for |
| --- | --- |
| Utility name (English / Spanish) | Header, page titles, emails |
| Public water system ID | Footer ("Water system ID …") |
| Phone, email, website, office address and hours | Footer, help boxes, the static site's email fallback |
| Default city / state / ZIP | Filled in for inventory rows without them, so geocoding works |
| Replacement deadline | "must be replaced by …" (defaults to 1 November 2037) |
| Replacement program (EN/ES) | Shown on lead and galvanized results and in the FAQ |
| Filter program (EN/ES) | Shown with the filter advice: where to get a free filter |
| Plan for unknown lines (EN/ES) | Shown on unknown results and in the FAQ |
| Basemap PMTiles URL | See [basemap.md](basemap.md) |
| Map center and zoom | Optional; otherwise the map fits all lines |
| Form endpoint for the static site | See [static-hosting.md](static-hosting.md) |
| Demo mode | Banner saying the data is fictional, and the demo street map |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `PIPETRACE_SECRET_KEY` | — (required) | Long random string used to sign sessions and forms. |
| `DATABASE_URL` | `postgis://pipetrace:pipetrace@localhost:5432/pipetrace` | PostGIS database. |
| `PIPETRACE_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated host names the site answers to. |
| `PIPETRACE_CSRF_TRUSTED_ORIGINS` | — | e.g. `https://leadlines.yourtown.gov` when behind HTTPS. |
| `PIPETRACE_SECURE` | `0` | `1` behind HTTPS: secure cookies, HSTS, redirect to HTTPS, trust `X-Forwarded-Proto`. |
| `PIPETRACE_SSL_REDIRECT` | `1` | With `PIPETRACE_SECURE=1`, redirect plain HTTP to HTTPS. |
| `PIPETRACE_HSTS_SECONDS` | `31536000` when secure | HSTS max-age. |
| `PIPETRACE_HSTS_PRELOAD` | `0` | Ask browsers to preload HSTS for the domain. |
| `PIPETRACE_DEBUG` | `0` | Development only. |
| `PIPETRACE_TIME_ZONE` | `America/Chicago` | For dates shown to residents and staff. |
| `PIPETRACE_GEOCODER` | `census` | `census`, `pelias` or `none`. |
| `PIPETRACE_CENSUS_BENCHMARK` | `Public_AR_Current` | Census geocoder benchmark. |
| `PIPETRACE_PELIAS_URL` | `http://localhost:4000` | Your Pelias server. |
| `PIPETRACE_PELIAS_API_KEY` | — | If your Pelias needs one. |
| `PIPETRACE_GEOCODE_BATCH_SIZE` | `250` | Addresses per geocoding request. |
| `PIPETRACE_NOTIFY_EMAILS` | — | Comma-separated staff addresses to email about new requests and photos (defaults to the utility email). |
| `PIPETRACE_EMAIL_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_USE_TLS` | — | SMTP server. Without a host, emails are printed to the log. |
| `PIPETRACE_FROM_EMAIL` | `pipetrace@localhost` | Sender address. |
| `PIPETRACE_SUBMISSIONS_PER_HOUR` | `10` | Forms one visitor may send per hour. |
| `PIPETRACE_MAX_PHOTO_MB` | `15` | Largest photo upload. |
| `PIPETRACE_MAX_IMPORT_MB` | `50` | Largest inventory spreadsheet. |
| `PIPETRACE_STATIC_SITE_ORIGINS` | `*` | Origins allowed to post forms to `/api/submit/` from a static export. |
| `PIPETRACE_CSP_CONNECT_SRC` | — | Extra origins for the Content-Security-Policy (e.g. a CDN hosting your basemap). |
| `PIPETRACE_BASEMAP_DIR` | `<media>/basemap` | Folder served at `/basemap/` with HTTP range support. |
| `PIPETRACE_MEDIA_ROOT` / `PIPETRACE_STATIC_ROOT` | `./media` / `./staticfiles` | Storage folders. |
| `PIPETRACE_LOG_LEVEL` | `INFO` | Log level. |

Docker image only:

| Variable | Default | Description |
| --- | --- | --- |
| `PIPETRACE_AUTO_MIGRATE` | `1` | Run migrations (and the two below) on start. |
| `PIPETRACE_ADMIN_USER` / `PIPETRACE_ADMIN_PASSWORD` / `PIPETRACE_ADMIN_EMAIL` | — | Create this admin if it doesn't exist. |
| `PIPETRACE_LOAD_DEMO` | `0` | Load the fictional Millbrook demo when the inventory is empty. |
