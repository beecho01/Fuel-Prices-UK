# Contributing

Thanks for considering a contribution to Fuel Prices UK.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -r requirements_dev.txt
```

`requirements_dev.txt` includes the Home Assistant/aiohttp/voluptuous
packages the integration's own modules import directly, plus the test-only
tools (`pytest`, `pytest-asyncio`, `aioresponses`, `ruff`).

## Running the test suite

```bash
pytest tests/ -v
```

The suite is pure-logic and mocked-API (via `aioresponses`) — no live
credentials or network access required. It covers:

- `price_parser.coerce_price` and the `location.py` pure helpers
- `api_client.py`'s payload-shaping functions (pagination, fuel-type
  mapping, date parsing, etc.)
- `FuelPricesAPI`'s refresh/pagination/incremental-fallback logic against a
  mocked Fuel Finder API, including rate-limit backoff and token caching
- the stale-data Repair's failure-counting logic

`config_flow.py` and `sensor.py`'s Home Assistant UI wiring are not covered
by automated tests currently — verify config flow and sensor changes
manually against a running Home Assistant instance.

## Linting

```bash
ruff check .
ruff format --check .    # add --fix / drop --check to apply
```

Both run in CI (`.github/workflows/test.yaml`) alongside `pytest`.
`hassfest` (`.github/workflows/hassfest.yml`) and HACS validation
(`.github/workflows/validate.yaml`) also run on every push/PR.

## Manual verification against the live API

`scripts/check_api_client.py` and `scripts/check_incremental_formats.py`
exercise the real Fuel Finder API end-to-end and need live credentials:

```bash
python scripts/check_api_client.py --client-id YOUR_ID --client-secret YOUR_SECRET
```

(or set `FUEL_FINDER_CLIENT_ID`/`FUEL_FINDER_CLIENT_SECRET`). Never commit
real credentials.

## Pull requests

- Keep `CHANGELOG.md` updated under an `[Unreleased]` heading for
  user-visible changes.
- Bump `manifest.json`'s `version` (and add a matching git tag) only when
  cutting a release, not per-PR.
- Prefer small, focused PRs; note any manual testing performed (which HA
  version, which config flow paths) in the PR description.
