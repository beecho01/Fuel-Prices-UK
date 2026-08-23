#!/usr/bin/env python3
"""Probe the Fuel Finder incremental endpoints with several timestamp formats.

The Fuel Finder API docs contradict themselves on what `effective-start-timestamp`
should look like for the incremental endpoints (GET /pfs and GET /pfs/fuel-prices):
the parameter schema says `format: date` (e.g. "2025-09-05"), but the hand-written
"Try it" example URL for the same operations shows "<YYYY-MM-DD HH:MM:SS>". This
script calls both incremental endpoints with several candidate formats and reports
the HTTP status + response body for each, so the real behaviour can be confirmed
against live credentials instead of guessed from the docs.

Usage:
    python scripts/check_incremental_formats.py --client-id ... --client-secret ...
    (or set FUEL_FINDER_CLIENT_ID / FUEL_FINDER_CLIENT_SECRET)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

# Mirrors custom_components/fuel_prices_uk/api_client.py. Kept as plain
# constants (rather than imported from the package) so this script runs
# with just `aiohttp` installed, without needing the homeassistant/voluptuous
# dev environment that importing the custom_components package pulls in.
API_BASE_URL = "https://www.fuel-finder.service.gov.uk"
TOKEN_ENDPOINT = "/api/v1/oauth/generate_access_token"
PFS_INFO_ENDPOINT = "/api/v1/pfs"
PFS_PRICES_ENDPOINT = "/api/v1/pfs/fuel-prices"
DEFAULT_HEADERS = {
    "User-Agent": "FuelPricesUK/1.0 (+https://github.com/beecho01/Fuel-Prices-UK)",
}

if sys.platform.startswith("win") and isinstance(
    asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy
):
    # aiodns requires SelectorEventLoop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

REQUEST_GAP_SECONDS = 2.5  # stay comfortably under the 100 req/min live limit
BODY_PREVIEW_CHARS = 300


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Fuel Finder incremental endpoints with candidate timestamp formats"
    )
    parser.add_argument("--client-id", default=os.getenv("FUEL_FINDER_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.getenv("FUEL_FINDER_CLIENT_SECRET"))
    parser.add_argument(
        "--base-url",
        default=API_BASE_URL,
        help="Override the API base URL (e.g. to point at the test environment)",
    )
    parser.add_argument(
        "--hours-ago",
        type=float,
        default=1.0,
        help="How far back the probed effective-start-timestamp should be (default: 1 hour)",
    )
    return parser.parse_args()


def _candidate_timestamps(reference: datetime) -> dict[str, str]:
    """Return {label: formatted value} for each timestamp format worth testing."""
    return {
        "bare date (YYYY-MM-DD) - matches OpenAPI schema": reference.strftime("%Y-%m-%d"),
        "space-separated (YYYY-MM-DD HH:MM:SS) - matches docs' example URL": reference.strftime("%Y-%m-%d %H:%M:%S"),
        "ISO 8601 with Z (YYYY-MM-DDTHH:MM:SSZ) - matches response payload format": reference.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "ISO 8601 with offset (YYYY-MM-DDTHH:MM:SS+00:00)": reference.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }


async def _get_access_token(session: aiohttp.ClientSession, base_url: str, client_id: str, client_secret: str) -> str:
    url = f"{base_url}{TOKEN_ENDPOINT}"
    headers = {**DEFAULT_HEADERS, "Content-Type": "application/json", "Accept": "application/json"}
    payload = {"client_id": client_id, "client_secret": client_secret}
    async with session.post(url, json=payload, headers=headers) as response:
        data = await response.json(content_type=None)
        if response.status >= 400:
            raise SystemExit(f"Token request failed ({response.status}): {data}")
        token_data = data.get("data") if isinstance(data, dict) else None
        if not isinstance(token_data, dict):
            token_data = data if isinstance(data, dict) else {}
        token = token_data.get("access_token")
        if not token:
            raise SystemExit(f"Token response did not include access_token: {data}")
        return token


def _preview(body: Any) -> str:
    text = str(body)
    if len(text) > BODY_PREVIEW_CHARS:
        return text[:BODY_PREVIEW_CHARS] + "...(truncated)"
    return text


async def _probe(
    session: aiohttp.ClientSession,
    base_url: str,
    token: str,
    endpoint: str,
    label: str,
    params: dict[str, Any],
) -> None:
    url = f"{base_url}{endpoint}"
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with session.get(url, params=params, headers=headers) as response:
        body = await response.json(content_type=None)
        status_flag = "OK " if response.status < 400 else "FAIL"
        print(f"  [{status_flag}] {label}")
        print(f"        request: GET {response.url}")
        print(f"        status:  {response.status}")
        print(f"        body:    {_preview(body)}")
    await asyncio.sleep(REQUEST_GAP_SECONDS)


async def main() -> None:
    args = _parse_args()
    if not args.client_id or not args.client_secret:
        raise SystemExit(
            "Missing credentials. Pass --client-id/--client-secret or set "
            "FUEL_FINDER_CLIENT_ID and FUEL_FINDER_CLIENT_SECRET."
        )

    base_url = args.base_url.rstrip("/")
    reference = datetime.now(UTC) - timedelta(hours=args.hours_ago)

    async with aiohttp.ClientSession() as session:
        print(f"Authenticating against {base_url} ...")
        token = await _get_access_token(session, base_url, args.client_id, args.client_secret)
        print("Got access token.\n")

        for endpoint, endpoint_name in (
            (PFS_INFO_ENDPOINT, "GET /pfs (station info)"),
            (PFS_PRICES_ENDPOINT, "GET /pfs/fuel-prices"),
        ):
            print(f"=== {endpoint_name} ===")

            print(" -- baseline: batch-number only (no effective-start-timestamp) --")
            await _probe(session, base_url, token, endpoint, "baseline (full snapshot, batch 1)", {"batch-number": 1})

            print(" -- incremental candidates --")
            for label, value in _candidate_timestamps(reference).items():
                await _probe(
                    session,
                    base_url,
                    token,
                    endpoint,
                    label,
                    {"batch-number": 1, "effective-start-timestamp": value},
                )
            print()

    print("Done. Compare status codes above - the format(s) returning 200 are what the live API actually accepts.")


if __name__ == "__main__":
    asyncio.run(main())
