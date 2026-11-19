# Vendored front-end libraries

Committed so Pipetrace needs no CDN, API key or JavaScript build step, and so a
static export works offline. Update with `scripts/vendor.sh`.

| Path | Package | Version | License |
| --- | --- | --- | --- |
| `maplibre-gl/` | [maplibre-gl](https://github.com/maplibre/maplibre-gl-js) (ES module build) | 6.19.0 | BSD-3-Clause (`maplibre-gl/LICENSE.txt`) |
| `pmtiles/pmtiles.js` | [pmtiles](https://github.com/protomaps/PMTiles) (browser bundle) | 4.5.0 | BSD-3-Clause |
| `protomaps-basemaps/basemaps.mjs` | [@protomaps/basemaps](https://github.com/protomaps/basemaps) | 5.7.2 | BSD-3-Clause |
| `basemaps-assets/fonts/` | Noto Sans glyphs from [protomaps/basemaps-assets](https://github.com/protomaps/basemaps-assets) (Latin ranges) | main | SIL Open Font License 1.1 (`fonts/OFL.txt`) |
| `basemaps-assets/sprites/v4/` | Basemap icons from protomaps/basemaps-assets | main | MIT ([tangrams/icons](https://github.com/tangrams/icons)) |

Source maps are removed to keep the repository small.
