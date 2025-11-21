"""Lightweight UK fuel price client without external pandas dependency.

Portions of this module are inspired by the uk-fuel-prices-api project
(LGPL-3.0)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FuelDataset:
    """Represents a retailer dataset and its public endpoint."""

    retailer: str
    url: str


# Official list as published by the CMA: https://www.gov.uk/guidance/access-fuel-price-data
FUEL_DATASETS: tuple[FuelDataset, ...] = (
    FuelDataset("Ascona Group", "https://fuelprices.asconagroup.co.uk/newfuel.json"),
    FuelDataset("Asda", "https://storelocator.asda.com/fuel_prices_data.json"),
    FuelDataset("bp", "https://www.bp.com/en_gb/united-kingdom/home/fuelprices/fuel_prices_data.json"),
    FuelDataset("Esso Tesco Alliance", "https://fuelprices.esso.co.uk/latestdata.json"),
    FuelDataset("JET Retail UK", "https://jetlocal.co.uk/fuel_prices_data.json"),
    FuelDataset("Karan Retail Ltd", "https://api.krl.live/integration/live_price/krl"),
    FuelDataset("Morrisons", "https://www.morrisons.com/fuel-prices/fuel.json"),
    FuelDataset("Moto", "https://moto-way.com/fuel-price/fuel_prices.json"),
    FuelDataset("Motor Fuel Group", "https://fuel.motorfuelgroup.com/fuel_prices_data.json"),
    FuelDataset("Rontec", "https://www.rontec-servicestations.co.uk/fuel-prices/data/fuel_prices_data.json"),
    FuelDataset("Sainsbury's", "https://api.sainsburys.co.uk/v1/exports/latest/fuel_prices_data.json"),
    FuelDataset("SGN", "https://www.sgnretail.uk/files/data/SGN_daily_fuel_prices.json"),
    FuelDataset("Shell", "https://www.shell.co.uk/fuel-prices-data.html"),
    FuelDataset("Tesco", "https://www.tesco.com/fuel_prices/fuel_prices_data.json"),
)

DEFAULT_HEADERS = {
    "User-Agent": "FuelPricesUK/1.0 (+https://github.com/beecho01/Fuel-Prices-UK)",
}

SUPPORTED_FUEL_TYPES = ("E10", "E5", "B7", "SDV")

DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)

CACHE_SECONDS = 3600


@dataclass
class StationRecord:
    """Internal lightweight representation of a fuel station."""

    data: Dict[str, Any]
    latitude: float
    longitude: float


class FuelPricesAPI:
    """Fetches and caches UK fuel price data using only aiohttp."""

    def __init__(
        self,
        hass: HomeAssistant | None = None,
        *,
        session: ClientSession | None = None,
        cache_seconds: int = CACHE_SECONDS,
    ) -> None:
        if session is None:
            if hass is None:
                raise ValueError("FuelPricesAPI requires either hass or an aiohttp session")
            session = async_get_clientsession(hass)
        self._session: ClientSession = session
        self._cache_seconds = cache_seconds
        self._stations: List[StationRecord] = []
        self._last_refresh: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def get_all_stations(self, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Return cached station dictionaries."""
        await self._ensure_data(force_refresh=force_refresh)
        return [record.data for record in self._stations]

    async def get_station_by_id(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Return a station by site identifier."""
        if not site_id:
            return None
        await self._ensure_data()
        for record in self._stations:
            station_id = (record.data.get("site_id") or "").lower()
            if station_id == site_id.lower():
                return record.data
        return None

    async def get_stations_within_radius(
        self, latitude: float, longitude: float, radius_km: float
    ) -> List[Dict[str, Any]]:
        """Return stations within the provided radius."""
        await self._ensure_data()
        matches: List[Tuple[float, Dict[str, Any]]] = []
        for record in self._stations:
            distance = _distance_km(latitude, longitude, record.latitude, record.longitude)
            if distance <= radius_km:
                station_copy = dict(record.data)
                station_copy["distance"] = round(distance, 2)
                matches.append((distance, station_copy))
        matches.sort(key=lambda item: item[0])
        return [item[1] for item in matches]

    async def search_stations(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Return stations matching the query across brand/address/postcode."""
        if not query:
            return []
        await self._ensure_data()
        needle = query.casefold()
        results = []
        for record in self._stations:
            haystacks = (
                str(record.data.get("brand", "")),
                str(record.data.get("address", "")),
                str(record.data.get("postcode", "")),
            )
            if any(needle in value.casefold() for value in haystacks if value):
                results.append(record.data)
                if len(results) >= limit:
                    break
        return results

    def sort_by_fuel_price(
        self, stations: Iterable[Dict[str, Any]], fuel_type: str
    ) -> List[Dict[str, Any]]:
        """Return stations sorted by fuel price for the provided fuel type."""
        if fuel_type not in SUPPORTED_FUEL_TYPES:
            return list(stations)

        sortable: List[Tuple[float, Dict[str, Any]]] = []
        for station in stations:
            price = _extract_price(station.get("prices", {}), fuel_type)
            if price is None:
                continue
            sortable.append((price, station))

        sortable.sort(key=lambda item: item[0])
        return [item[1] for item in sortable]

    async def _ensure_data(self, *, force_refresh: bool = False) -> None:
        """Refresh cached data when stale."""
        if not force_refresh and self._data_fresh:
            return
        async with self._lock:
            if not force_refresh and self._data_fresh:
                return
            await self._refresh()

    @property
    def _data_fresh(self) -> bool:
        if self._last_refresh is None:
            return False
        return (datetime.now(timezone.utc) - self._last_refresh).total_seconds() < self._cache_seconds

    async def _refresh(self) -> None:
        tasks = [self._fetch_endpoint(dataset) for dataset in FUEL_DATASETS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        stations: List[StationRecord] = []
        errors: List[Tuple[FuelDataset, Exception]] = []
        for dataset, result in zip(FUEL_DATASETS, results):
            if isinstance(result, Exception):
                errors.append((dataset, result))
                continue
            if isinstance(result, list):
                stations.extend(result)
            else:
                _LOGGER.debug("Unexpected payload type from endpoint: %s", type(result))
        if not stations:
            _LOGGER.error("Fuel prices fetch returned no data from any retailer feed")
            return
        if errors:
            if len(errors) == len(FUEL_DATASETS):
                last_dataset, last_err = errors[-1]
                _LOGGER.error(
                    "All %s retailer feeds failed; last error from %s: %s",
                    len(FUEL_DATASETS),
                    last_dataset.retailer,
                    last_err,
                )
            else:
                _LOGGER.info(
                    "Skipped %s/%s retailer feeds due to HTTP errors (enable debug logs for details)",
                    len(errors),
                    len(FUEL_DATASETS),
                )
                for dataset, err in errors:
                    _LOGGER.debug("Suppressed error for %s (%s): %s", dataset.retailer, dataset.url, err)
        self._stations = stations
        self._last_refresh = datetime.now(timezone.utc)

    async def _fetch_endpoint(self, dataset: FuelDataset) -> List[StationRecord]:
        timeout = ClientTimeout(total=15)
        try:
            async with self._session.get(dataset.url, timeout=timeout, headers=DEFAULT_HEADERS) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (ClientError, asyncio.TimeoutError) as err:
            raise RuntimeError(f"Request failed for {dataset.url}: {err}") from err
        except Exception as err:  # pragma: no cover - defensive
            raise RuntimeError(f"Unhandled error fetching {dataset.url}: {err}") from err

        stations = payload.get("stations")
        if not isinstance(stations, list):
            return []
        dataset_updated = _parse_datetime(payload.get("last_updated"))
        normalized: List[StationRecord] = []
        for entry in stations:
            station = _normalize_station(entry, dataset.url, dataset_updated)
            latitude = _safe_float(station.get("latitude"))
            longitude = _safe_float(station.get("longitude"))
            if latitude is None or longitude is None:
                continue
            normalized.append(StationRecord(data=station, latitude=latitude, longitude=longitude))
        return normalized


def _normalize_station(entry: Dict[str, Any], endpoint: str, dataset_timestamp: Optional[str]) -> Dict[str, Any]:
    station = dict(entry)
    station.setdefault("source_endpoint", endpoint)

    if dataset_timestamp and not station.get("last_updated"):
        station["last_updated"] = dataset_timestamp
    elif isinstance(station.get("last_updated"), str):
        station["last_updated"] = _parse_datetime(station["last_updated"]) or station["last_updated"]

    location = station.pop("location", None)
    if isinstance(location, dict):
        for key in ("address", "postcode", "latitude", "longitude", "town"):
            station.setdefault(key, location.get(key))

    station["prices"] = _normalize_prices(station.get("prices"))
    return station


def _normalize_prices(prices: Any) -> Dict[str, Any]:
    if isinstance(prices, dict):
        return prices
    if isinstance(prices, list):
        merged: Dict[str, Any] = {}
        for item in prices:
            if isinstance(item, dict) and "fuelType" in item:
                merged[item["fuelType"]] = item
        return merged
    return {}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        # Interpret as UNIX timestamp seconds
        try:
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            return dt.isoformat()
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        stripped = value.strip()
        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(stripped, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
    return None


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    km = 6371 * c
    return round(km, 3)


def _extract_price(prices: Dict[str, Any], fuel_type: str) -> Optional[float]:
    price_entry = prices.get(fuel_type)
    if isinstance(price_entry, dict):
        value = price_entry.get("price") or price_entry.get("value")
    else:
        value = price_entry
    try:
        if value is None:
            return None
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price > 100:  # Values returned in pence
        price = price / 100
    return round(price, 3)
