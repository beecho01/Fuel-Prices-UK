#!/usr/bin/env python3
"""Quick manual verification script for the Fuel Prices API client."""
from __future__ import annotations

import asyncio
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


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        api = FuelPricesAPI(session=session)
        stations = await api.get_all_stations(force_refresh=True)
        if not stations:
            raise SystemExit("No stations returned from data sources")

        print(f"Retrieved {len(stations)} stations across all providers")
        sample = stations[0]
        print(
            "Sample station:",
            sample.get("name") or sample.get("brand") or sample.get("site_id"),
            "-",
            sample.get("postcode"),
        )


if __name__ == "__main__":
    asyncio.run(main())
