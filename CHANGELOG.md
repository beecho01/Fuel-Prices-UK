# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions use the
`YYYY.MM.DD` scheme HACS integrations conventionally use.

## [2026.08.23] - 2026-08-23

### Fixed

- Incremental refresh (`GET /pfs` and `GET /pfs/fuel-prices` with
  `effective-start-timestamp`) no longer falls back to an expensive full
  nationwide snapshot on almost every poll. A 404 on batch 1 for an
  incremental request is now correctly treated as "no updates in this
  window" instead of a hard failure — confirmed against the live Fuel
  Finder API, this happens regardless of timestamp format and is how the
  API signals an empty incremental result. This was the root cause of
  [#14](https://github.com/beecho01/Fuel-Prices-UK/issues/14).
- `effective-start-timestamp` is now sent as a full `YYYY-MM-DD HH:MM:SS`
  timestamp (matching the API docs' worked request example) rather than a
  bare date.
- Removed unused `"dependencies": ["http", "frontend"]` from `manifest.json`
  and added the previously-implicit `requests` runtime requirement
  explicitly.

### Added

- A persistent Repair (Settings → Repairs) is now raised when a config
  entry's refresh has failed for 3+ consecutive cycles, so stale data is
  visible in the UI instead of only in the logs — requested by commenters
  on [#14](https://github.com/beecho01/Fuel-Prices-UK/issues/14). Clears
  automatically on the next successful refresh.
- Automated test suite (`tests/`, run via `pytest`) covering price/payload
  parsing, pagination and incremental-fallback logic, rate-limit/token
  handling, and the new stale-data repair — see `CONTRIBUTING.md`.
- CI: `pytest` and `ruff` (lint + format) now run on every push/PR.
- `strings.json` added as the canonical translation source (previously only
  `translations/en.json` existed), fixing `hassfest` validation, which is
  now re-enabled in CI.
- `scripts/check_incremental_formats.py`: a standalone diagnostic tool for
  probing the live Fuel Finder API with several `effective-start-timestamp`
  formats.

## [2026.05.22] - 2026-05-22

### Added

- Global OAuth token cache shared across config entries with the same
  credentials, fixing a token-thrashing loop when running multiple
  locations ([#8](https://github.com/beecho01/Fuel-Prices-UK/issues/8)).
- Global request-rate lock and 429 cooldown shared across all API client
  instances, plus staggered startup refreshes, to reduce rate-limit
  failures on setup ([#11](https://github.com/beecho01/Fuel-Prices-UK/issues/11)).
- Custom template entity rows for richer fuel price display.

## [2026.03.16] - 2026-03-16

### Added

- Nearest-station distance-ranked sensors (configurable count, 0-5).
- Device tracker location method for a live, moving search centre.
- YAML configuration import (single or multiple instances).
- `max_data_age_days` option to filter out stale station prices.

### Fixed

- Cheapest-price sensors now honour ranked-count options at runtime.
- Distance attribute converted to miles for consistency across sensors.

## [2026.03.14] - 2026-03-14

### Added

- Background startup refresh with an automatic delayed retry, so entities
  appear promptly without blocking config entry setup.
- Configurable ranked "cheapest" sensors (2nd/3rd/... up to 5th cheapest
  per fuel type).

### Fixed

- Pagination now treats a 404 on batch 2+ as end-of-pages instead of a
  fatal error during setup.
- Response parsing and fuel-price merging fixed for the first refresh.

## [2025.11.24] - 2025-11-24

### Changed

- Reworked the integration around the UK Government's new Fuel Finder
  OAuth-protected API, replacing the previous data source.

## [2025.11.23] - 2025-11-22

Initial tagged release.
