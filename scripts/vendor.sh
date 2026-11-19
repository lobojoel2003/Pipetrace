#!/usr/bin/env bash
# Refresh the vendored map libraries in pipetrace/static/pipetrace/vendor/.
# Usage: scripts/vendor.sh [maplibre-version] [pmtiles-version] [basemaps-version]
set -euo pipefail
MAPLIBRE=${1:-6.19.0}
PMTILES=${2:-4.5.0}
BASEMAPS=${3:-5.7.2}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
V="$ROOT/pipetrace/static/pipetrace/vendor"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cd "$TMP"
npm pack "maplibre-gl@$MAPLIBRE" "pmtiles@$PMTILES" "@protomaps/basemaps@$BASEMAPS" --silent
for f in *.tgz; do mkdir -p "${f%.tgz}" && tar -xzf "$f" -C "${f%.tgz}"; done

mkdir -p "$V/maplibre-gl" "$V/pmtiles" "$V/protomaps-basemaps"
cp maplibre-gl-*/package/dist/{maplibre-gl.mjs,maplibre-gl-worker.mjs,maplibre-gl.css} \
   maplibre-gl-*/package/LICENSE.txt "$V/maplibre-gl/"
cp pmtiles-*/package/dist/pmtiles.js "$V/pmtiles/pmtiles.js"
cp protomaps-basemaps-*/package/dist/esm/index.js "$V/protomaps-basemaps/basemaps.mjs"
sed -i '/^\/\/# sourceMappingURL=/d' "$V"/maplibre-gl/*.mjs "$V/pmtiles/pmtiles.js" \
  "$V/protomaps-basemaps/basemaps.mjs"

ASSETS=https://raw.githubusercontent.com/protomaps/basemaps-assets/main
for font in "Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic"; do
  mkdir -p "$V/basemaps-assets/fonts/$font"
  for range in 0-255 256-511 8192-8447; do
    curl -fsSL -o "$V/basemaps-assets/fonts/$font/$range.pbf" "$ASSETS/fonts/${font// /%20}/$range.pbf"
  done
done
curl -fsSL -o "$V/basemaps-assets/fonts/OFL.txt" "$ASSETS/fonts/OFL.txt"
mkdir -p "$V/basemaps-assets/sprites/v4"
for name in light dark; do
  for suffix in "" "@2x"; do
    for ext in json png; do
      curl -fsSL -o "$V/basemaps-assets/sprites/v4/$name$suffix.$ext" \
        "$ASSETS/sprites/v4/$name$suffix.$ext"
    done
  done
done
echo "Vendored maplibre-gl $MAPLIBRE, pmtiles $PMTILES, @protomaps/basemaps $BASEMAPS."
echo "Update the versions in $V/VENDORED.md."
