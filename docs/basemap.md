# A free basemap with Protomaps

Pipetrace draws the service lines with [MapLibre GL](https://maplibre.org). For
streets and place names underneath, it uses a [Protomaps](https://protomaps.com)
basemap: OpenStreetMap data in a single `.pmtiles` file that you host yourself. There
is no tile server, no API key and no per-view fee. The browser fetches just the parts
it needs with HTTP range requests.

Without a basemap the map still works and shows the points on a plain background.

## 1. Cut out your service area

Install the [`pmtiles` command-line tool](https://github.com/protomaps/go-pmtiles/releases),
then let Pipetrace print the command for your inventory's area:

```bash
pipetrace basemap
```

It prints something like:

```bash
pmtiles extract https://build.protomaps.com/YYYYMMDD.pmtiles /data/media/basemap/area.pmtiles \
  --bbox=-89.2,39.9,-88.9,40.1 --maxzoom=15
```

Replace `YYYYMMDD` with a recent build from
[maps.protomaps.com/builds](https://maps.protomaps.com/builds) and run it. A small
town is usually a few megabytes.

## 2. Point Pipetrace at it

Put the file in the basemap folder (`/data/media/basemap/` in Docker, or
`PIPETRACE_BASEMAP_DIR`), then set **Site settings → Basemap PMTiles URL** to:

```
/basemap/area.pmtiles
```

Pipetrace serves that folder with range-request support, and the static export copies
the file, so static sites get the basemap too.

You can also host the file on a CDN or object storage that supports range requests
(and CORS) and use its full URL; add the CDN's origin to `PIPETRACE_CSP_CONNECT_SRC`.

## Attribution

The map shows "© OpenStreetMap" and "Protomaps" as their licences require. Fonts and
icons are vendored in `pipetrace/static/pipetrace/vendor/basemaps-assets/`.
