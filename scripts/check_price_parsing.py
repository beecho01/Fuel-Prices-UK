"""Validate sample retailer payloads for price extraction and metadata sanity."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.fuel_prices_uk.price_parser import coerce_price  # noqa: E402
from custom_components.fuel_prices_uk.api_client import _parse_datetime  # type: ignore  # noqa: E402

EXAMPLES_DIR = REPO_ROOT / "examples"


def _iter_price_entries(station: Dict[str, Any]):
    prices = station.get("prices")
    if isinstance(prices, dict):
        for fuel_type, payload in prices.items():
            yield fuel_type, payload


def _extract_lat_lon(station: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    lat = station.get("latitude") or station.get("lat")
    lon = station.get("longitude") or station.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)

    location = station.get("location")
    if isinstance(location, dict):
        lat = location.get("latitude") or location.get("lat")
        lon = location.get("longitude") or location.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    return None, None


def _extract_timestamp_sources(*entries: Optional[Dict[str, Any]]) -> Optional[Any]:
    keys = ("last_updated", "timestamp", "updated", "date")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in keys:
            value = entry.get(key)
            if value:
                return value
    return None


def _gather_station_checks(station: Dict[str, Any]) -> Iterable[str]:
    lat, lon = _extract_lat_lon(station)
    if lat is None or lon is None:
        yield "missing latitude/longitude"


def _gather_price_checks(
    sample_name: str, station_id: str, fuel_type: str, payload: Any, station: Dict[str, Any]
) -> Iterable[str]:
    parsed = coerce_price(payload)
    if parsed is None:
        yield f"{sample_name} :: {station_id} :: {fuel_type} -> could not coerce from {payload!r}"
        return
    if not 0.5 <= parsed <= 3.0:
        yield (
            f"{sample_name} :: {station_id} :: {fuel_type} -> implausible GBP value {parsed}."
            " Expected price per litre between £0.50 and £3.00"
        )

    payload_dict = payload if isinstance(payload, dict) else None
    timestamp_source = _extract_timestamp_sources(payload_dict, station)
    if timestamp_source is not None and _parse_datetime(timestamp_source) is None:
        yield (
            f"{sample_name} :: {station_id} :: {fuel_type} -> timestamp {timestamp_source!r}"
            " could not be normalised"
        )


def main() -> int:
    if not EXAMPLES_DIR.exists():
        print(f"Examples directory not found: {EXAMPLES_DIR}")
        return 1

    failures: list[str] = []
    total_prices = 0
    total_stations = 0
    sample_files = sorted(EXAMPLES_DIR.glob("*.json"))
    if not sample_files:
        print(f"No sample JSON files found in {EXAMPLES_DIR}")
        return 1

    for sample in sample_files:
        try:
            data = json.loads(sample.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            failures.append(f"{sample.name}: invalid JSON ({err})")
            continue

        stations = data.get("stations")
        if not isinstance(stations, list):
            failures.append(f"{sample.name}: missing 'stations' array")
            continue

        for station in stations:
            total_stations += 1
            station_failures = list(_gather_station_checks(station))
            if station_failures:
                for failure in station_failures:
                    site_id = station.get("site_id") or station.get("id") or "<unknown-site>"
                    failures.append(f"{sample.name} :: {site_id} -> {failure}")

            site_id = station.get("site_id") or station.get("id") or "<unknown-site>"
            for fuel_type, payload in _iter_price_entries(station):
                total_prices += 1
                failures.extend(_gather_price_checks(sample.name, site_id, fuel_type, payload, station))

    if failures:
        print("Sample validation failed for the following entries:\n")
        for failure in failures:
            print(f" - {failure}")
        print(
            f"\nChecked {total_prices} price entries and {total_stations} stations across {len(sample_files)} files."
        )
        return 1

    print(
        f"Successfully validated {total_prices} price entries and {total_stations} stations across {len(sample_files)} files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
