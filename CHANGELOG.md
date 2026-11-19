# Changelog

All notable changes to Pipetrace are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Every release also carries a CI build
number (shown in the site footer, `/healthz` and the release title).

## [Unreleased]

## [1.0.0] - 2026-11-19

The first release: everything a small water system needs to publish its lead
service line inventory.

### Added

- **Address lookup** with suggestions as you type, tolerant of abbreviations
  ("Street"/"St"), missing city or ZIP, unit numbers and small typos.
- **One plain answer per address** (lead, galvanized requiring replacement, not
  lead, or unknown) with a colour, a shape and an icon, what it means, what to do
  today, the replacement schedule and the utility's own programs.
- **Two-minute coin-and-magnet guide** with illustrations and an interactive
  "what did you find?" helper, and a **photo form** so residents can send their
  pipe to staff. Photos are re-encoded and stripped of location data.
- **Inspection request form** with spam protection and email notifications.
- **Map** built with MapLibre GL and an optional self-hosted Protomaps (PMTiles)
  basemap: no tile service, API key or map fees. Colour-blind-safe status palette
  with distinct marker shapes, in light and dark themes.
- **Inventory importer** for EPA-template and home-grown spreadsheets (.xlsx and
  .csv): finds the header row under titles and group headers, guesses every column,
  lets staff fix the column mapping and the meaning of each code, previews the
  result, and imports in "update" or "replace" mode. Mappings are remembered for
  the next upload of the same layout.
- **Geocoding** with the free U.S. Census Bureau geocoder (batch API) or a
  self-hosted Pelias server, run in small batches from the staff page or
  `manage.py geocode`.
- **Staff area**: dashboard, inventory table, CSV export, inspection requests,
  photo review that can update the inventory, and geocoding progress.
- **Static export** (`manage.py export_static` or a button in the staff area) that
  writes the whole site, both languages, as plain files for free hosting, with
  in-browser search and forms that post to a Pipetrace server or open an email.
- **English and Spanish** throughout, including the staff tools.
- Fictional **"Millbrook" demo** dataset and street map (`manage.py load_demo`).
- Docker image (multi-arch) and Docker Compose setup with PostGIS.
- CI (lint, tests on Python 3.12 and 3.13 against PostGIS, browser tests of the
  static site, Docker smoke test) and tagged releases with build numbers, wheels,
  a demo site bundle and container images.

[Unreleased]: https://github.com/lobojoel2003/Pipetrace/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lobojoel2003/Pipetrace/releases/tag/v1.0.0
