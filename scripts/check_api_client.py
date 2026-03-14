#!/usr/bin/env python3
"""Quick manual verification script for the Fuel Prices API client."""
from __future__ import annotations

import asyncio
import argparse
import os
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_components.fuel_prices_uk.api_client import FuelPricesAPI  # noqa: E402


if sys.platform.startswith("win") and isinstance(
    asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy
):
    # aiodns requires SelectorEventLoop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Fuel Finder API connectivity")
    parser.add_argument("--client-id", default=os.getenv("FUEL_FINDER_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.getenv("FUEL_FINDER_CLIENT_SECRET"))
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    if not args.client_id or not args.client_secret:
        raise SystemExit(
            "Missing credentials. Pass --client-id/--client-secret or set "
            "FUEL_FINDER_CLIENT_ID and FUEL_FINDER_CLIENT_SECRET."
        )

    async with aiohttp.ClientSession() as session:
        api = FuelPricesAPI(
            session=session,
            client_id=args.client_id,
            client_secret=args.client_secret,
        )
        stations = await api.get_all_stations(force_refresh=True)
        if not stations:
            raise SystemExit("No stations returned from data sources")

        print(f"Retrieved {len(stations)} stations across all providers")
        sample = stations[0]
        print(
            "Sample station:",
            sample.get("name") or sample.get("trading_name") or sample.get("brand") or sample.get("site_id"),
            "-",
            sample.get("postcode"),
        )


if __name__ == "__main__":
    asyncio.run(main())
