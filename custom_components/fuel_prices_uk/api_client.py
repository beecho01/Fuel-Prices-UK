"""Fuel Finder (UK Government) API client for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .price_parser import coerce_price

_LOGGER = logging.getLogger(__name__)


API_BASE_URL = "https://www.fuel-finder.service.gov.uk"
TOKEN_ENDPOINT = "/api/v1/oauth/generate_access_token"
PFS_INFO_ENDPOINT = "/api/v1/pfs"
PFS_PRICES_ENDPOINT = "/api/v1/pfs/fuel-prices"

DEFAULT_HEADERS = {
    "User-Agent": "FuelPricesUK/1.0 (+https://github.com/beecho01/Fuel-Prices-UK)",
}

SUPPORTED_FUEL_TYPES = ("E10", "E5", "B7", "SDV")
FUEL_TYPE_MAP = {
    "E10": "E10",
    "E5": "E5",
    "B7": "B7",
    "B7_STANDARD": "B7",
    "SDV": "SDV",
    "B7_PREMIUM": "SDV",
}

DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)

CACHE_SECONDS = 3600
BATCH_SIZE = 500
MAX_BATCHES = 80
MIN_REQUEST_INTERVAL_SECONDS = 2.05
DEFAULT_TIMEOUT_SECONDS = 20
MAX_429_RETRIES = 3
DEFAULT_429_BACKOFF_SECONDS = 3.0


@dataclass
class StationRecord:
    """Internal lightweight representation of a fuel station."""

    data: Dict[str, Any]
    latitude: float
    longitude: float


class FuelPricesAPI:
    """Fetches and caches Fuel Finder station and fuel price data."""

    def __init__(
        self,
        hass: HomeAssistant | None = None,
        *,
        session: ClientSession | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        cache_seconds: int = CACHE_SECONDS,
        base_url: str = API_BASE_URL,
    ) -> None:
        if session is None:
            if hass is None:
                raise ValueError("FuelPricesAPI requires either hass or an aiohttp session")
            session = async_get_clientsession(hass)
        self._session: ClientSession = session
        self._base_url = base_url.rstrip("/")
        self._client_id = (client_id or "").strip()
        self._client_secret = (client_secret or "").strip()
        self._cache_seconds = cache_seconds
        self._stations: List[StationRecord] = []
        self._station_index: Dict[str, Dict[str, Any]] = {}
        self._last_refresh: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._token_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._last_request_at: Optional[float] = None

    async def get_all_stations(self, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Return cached station dictionaries."""
        await self._ensure_data(force_refresh=force_refresh)
        return list(self._station_index.values())

    async def get_station_by_id(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Return a station by site identifier."""
        if not site_id:
            return None
        await self._ensure_data()
        station = self._station_index.get(site_id)
        if station is not None:
            return station
        site_id_normalized = site_id.lower()
        for key, payload in self._station_index.items():
            if key.lower() == site_id_normalized:
                return payload
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
        for record in self._station_index.values():
            haystacks = (
                str(record.get("brand", "")),
                str(record.get("address", "")),
                str(record.get("postcode", "")),
            )
            if any(needle in value.casefold() for value in haystacks if value):
                results.append(record)
                if len(results) >= limit:
                    break
        return results

    async def async_validate_credentials(self) -> bool:
        """Validate OAuth credentials against Fuel Finder token endpoint."""
        await self._get_access_token(force_refresh=True)
        return True

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
        is_incremental = bool(self._last_refresh and self._station_index)
        incremental_date = self._last_refresh.date().isoformat() if self._last_refresh else None

        try:
            if is_incremental and incremental_date:
                stations = await self._fetch_station_info(effective_start=incremental_date)
                prices = await self._fetch_station_prices(effective_start=incremental_date)
                if not stations and not prices:
                    _LOGGER.debug("Fuel Finder incremental refresh reported no station or price updates")
                    self._last_refresh = datetime.now(timezone.utc)
                    return
                self._merge_station_info(stations)
                self._merge_station_prices(prices)
            else:
                stations = await self._fetch_station_info()
                prices = await self._fetch_station_prices()
                new_index: Dict[str, Dict[str, Any]] = {}
                self._station_index = new_index
                self._merge_station_info(stations)
                self._merge_station_prices(prices)
        except RuntimeError as err:
            if is_incremental:
                _LOGGER.warning(
                    "Fuel Finder incremental refresh failed (%s); retrying with full snapshot",
                    err,
                )
                stations = await self._fetch_station_info()
                prices = await self._fetch_station_prices()
                self._station_index = {}
                self._merge_station_info(stations)
                self._merge_station_prices(prices)
            else:
                raise

        if not self._station_index:
            raise RuntimeError("Fuel Finder returned no stations")

        station_records: List[StationRecord] = []
        for station in self._station_index.values():
            latitude = _safe_float(station.get("latitude"))
            longitude = _safe_float(station.get("longitude"))
            if latitude is None or longitude is None:
                continue
            station_records.append(StationRecord(data=station, latitude=latitude, longitude=longitude))

        if not station_records:
            raise RuntimeError("Fuel Finder response had no stations with usable coordinates")

        self._stations = station_records
        self._last_refresh = datetime.now(timezone.utc)

    async def _fetch_station_info(self, *, effective_start: str | None = None) -> List[Dict[str, Any]]:
        return await self._fetch_batched_resource(PFS_INFO_ENDPOINT, effective_start=effective_start)

    async def _fetch_station_prices(self, *, effective_start: str | None = None) -> List[Dict[str, Any]]:
        return await self._fetch_batched_resource(PFS_PRICES_ENDPOINT, effective_start=effective_start)

    async def _fetch_batched_resource(
        self, endpoint: str, *, effective_start: str | None = None
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        batch_number = 1
        while batch_number <= MAX_BATCHES:
            params: Dict[str, Any] = {"batch-number": batch_number}
            if effective_start:
                params["effective-start-timestamp"] = effective_start

            payload = await self._api_get(endpoint, params=params)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                if batch_number == 1:
                    raise RuntimeError(
                        f"Unexpected response shape from {endpoint}; expected object with list in data"
                    )
                break

            batch_records = [item for item in data if isinstance(item, dict)]
            if not batch_records:
                break
            records.extend(batch_records)

            if len(batch_records) < BATCH_SIZE:
                break
            batch_number += 1

        if batch_number > MAX_BATCHES:
            _LOGGER.warning(
                "Stopped paging %s at MAX_BATCHES=%s to avoid runaway API loops",
                endpoint,
                MAX_BATCHES,
            )
        return records

    async def _api_get(self, endpoint: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
        timeout = ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)
        response_payload: Dict[str, Any] = {}

        for attempt in (1, 2):
            token = await self._get_access_token(force_refresh=(attempt == 2))
            headers = {
                **DEFAULT_HEADERS,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            url = f"{self._base_url}{endpoint}"
            token_rejected = False
            for retry_count in range(MAX_429_RETRIES + 1):
                backoff_seconds: float | None = None
                try:
                    async with self._request_lock:
                        await self._respect_rate_limit()
                        async with self._session.get(url, params=params, timeout=timeout, headers=headers) as response:
                            response_payload = await _parse_json_response(response)
                            if response.status in (401, 403) and attempt == 1:
                                _LOGGER.info("Fuel Finder token rejected, refreshing OAuth token and retrying")
                                token_rejected = True
                                break

                            if response.status == 429:
                                if retry_count >= MAX_429_RETRIES:
                                    raise RuntimeError(
                                        f"GET {endpoint} failed (429): rate limit exceeded after retries"
                                    )
                                backoff_seconds = _extract_retry_after_seconds(response)
                                _LOGGER.warning(
                                    "Fuel Finder returned 429 for %s; retrying in %.2fs (attempt %s/%s)",
                                    endpoint,
                                    backoff_seconds,
                                    retry_count + 1,
                                    MAX_429_RETRIES,
                                )
                            elif response.status >= 400:
                                message = _extract_api_error(response_payload) or response.reason
                                raise RuntimeError(f"GET {endpoint} failed ({response.status}): {message}")
                            else:
                                return response_payload
                except (ClientError, asyncio.TimeoutError) as err:
                    raise RuntimeError(f"GET {endpoint} failed: {err}") from err

                if backoff_seconds is not None:
                    await asyncio.sleep(backoff_seconds)

            if token_rejected and attempt == 1:
                continue

        raise RuntimeError(f"GET {endpoint} failed after token refresh")

    async def _respect_rate_limit(self) -> None:
        now = asyncio.get_running_loop().time()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_at = asyncio.get_running_loop().time()

    async def _get_access_token(self, *, force_refresh: bool = False) -> str:
        if not self._client_id or not self._client_secret:
            raise RuntimeError("Fuel Finder API credentials are missing")

        if not force_refresh and self._token_is_valid:
            return self._access_token or ""

        async with self._token_lock:
            if not force_refresh and self._token_is_valid:
                return self._access_token or ""

            timeout = ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)
            headers = {**DEFAULT_HEADERS, "Content-Type": "application/json", "Accept": "application/json"}
            payload = {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
            token_url = f"{self._base_url}{TOKEN_ENDPOINT}"

            try:
                async with self._request_lock:
                    await self._respect_rate_limit()
                    async with self._session.post(token_url, json=payload, timeout=timeout, headers=headers) as response:
                        response_payload = await _parse_json_response(response)
                        if response.status >= 400:
                            message = _extract_api_error(response_payload) or response.reason
                            raise RuntimeError(
                                f"Fuel Finder token request failed ({response.status}): {message}"
                            )
            except (ClientError, asyncio.TimeoutError) as err:
                raise RuntimeError(f"Fuel Finder token request failed: {err}") from err

            token_data = response_payload.get("data") if isinstance(response_payload, dict) else None
            if not isinstance(token_data, dict):
                token_data = response_payload if isinstance(response_payload, dict) else {}

            token = token_data.get("access_token")
            if not token or not isinstance(token, str):
                raise RuntimeError("Fuel Finder token response did not include access_token")

            expires_in = token_data.get("expires_in")
            try:
                expiry_seconds = max(int(expires_in), 120) if expires_in is not None else 3600
            except (TypeError, ValueError):
                expiry_seconds = 3600

            self._access_token = token
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds - 60)
            return token

    @property
    def _token_is_valid(self) -> bool:
        return bool(
            self._access_token
            and self._token_expiry
            and datetime.now(timezone.utc) < self._token_expiry
        )

    def _merge_station_info(self, rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            node_id = str(row.get("node_id") or "").strip()
            if not node_id:
                continue

            existing = self._station_index.get(node_id)
            if not isinstance(existing, dict):
                existing = {
                    "site_id": node_id,
                    "id": node_id,
                    "prices": {},
                }

            location_obj = row.get("location")
            location: Dict[str, Any] = location_obj if isinstance(location_obj, dict) else {}
            address = _format_address(location)

            existing["site_id"] = node_id
            existing["id"] = node_id
            existing["name"] = row.get("trading_name") or existing.get("name")
            existing["trading_name"] = row.get("trading_name") or existing.get("trading_name")
            existing["brand"] = row.get("brand_name") or row.get("trading_name") or existing.get("brand")
            existing["address"] = address or existing.get("address")
            existing["postcode"] = location.get("postcode") or existing.get("postcode")
            existing["latitude"] = location.get("latitude") if location else existing.get("latitude")
            existing["longitude"] = location.get("longitude") if location else existing.get("longitude")
            existing["location"] = {
                "address": address,
                "address_line_1": location.get("address_line_1"),
                "address_line_2": location.get("address_line_2"),
                "town": location.get("city"),
                "city": location.get("city"),
                "country": location.get("country"),
                "county": location.get("county"),
                "postcode": location.get("postcode"),
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
            }
            existing["fuel_types"] = row.get("fuel_types") if isinstance(row.get("fuel_types"), list) else []
            existing["amenities"] = row.get("amenities") if isinstance(row.get("amenities"), list) else []
            existing["opening_times"] = row.get("opening_times") if isinstance(row.get("opening_times"), dict) else {}
            existing["source_endpoint"] = f"{self._base_url}{PFS_INFO_ENDPOINT}"

            if not isinstance(existing.get("prices"), dict):
                existing["prices"] = {}

            self._station_index[node_id] = existing

    def _merge_station_prices(self, rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            node_id = str(row.get("node_id") or "").strip()
            if not node_id:
                continue

            station = self._station_index.get(node_id)
            if not isinstance(station, dict):
                station = {
                    "site_id": node_id,
                    "id": node_id,
                    "name": row.get("trading_name"),
                    "trading_name": row.get("trading_name"),
                    "brand": row.get("trading_name"),
                    "prices": {},
                    "source_endpoint": f"{self._base_url}{PFS_PRICES_ENDPOINT}",
                }

            station_prices = station.get("prices")
            prices: Dict[str, Any] = station_prices if isinstance(station_prices, dict) else {}
            last_updated = station.get("last_updated") if isinstance(station.get("last_updated"), str) else None

            raw_fuel_prices = row.get("fuel_prices")
            fuel_prices: List[Any] = raw_fuel_prices if isinstance(raw_fuel_prices, list) else []
            for fuel_entry in fuel_prices:
                if not isinstance(fuel_entry, dict):
                    continue

                source_fuel_type = str(fuel_entry.get("fuel_type") or "").upper()
                target_fuel_type = FUEL_TYPE_MAP.get(source_fuel_type)
                if not target_fuel_type:
                    continue

                parsed_price = coerce_price(fuel_entry.get("price"))
                if parsed_price is None:
                    continue

                price_last_updated = _parse_datetime(fuel_entry.get("price_last_updated"))
                effective_timestamp = _parse_datetime(fuel_entry.get("price_change_effective_timestamp"))
                prices[target_fuel_type] = {
                    "price": parsed_price,
                    "source_fuel_type": source_fuel_type,
                    "last_updated": price_last_updated,
                    "price_change_effective_timestamp": effective_timestamp,
                }
                last_updated = _latest_iso(last_updated, price_last_updated)

            station["prices"] = prices
            station["last_updated"] = last_updated
            station["source_endpoint"] = f"{self._base_url}{PFS_PRICES_ENDPOINT}"
            self._station_index[node_id] = station


async def async_validate_api_credentials(
    hass: HomeAssistant, client_id: str, client_secret: str
) -> bool:
    """Validate Fuel Finder OAuth credentials."""
    if not client_id or not client_secret:
        return False
    api = FuelPricesAPI(hass=hass, client_id=client_id, client_secret=client_secret, cache_seconds=0)
    try:
        await api.async_validate_credentials()
    except Exception as err:
        _LOGGER.warning("Fuel Finder credential validation failed: %s", err)
        return False
    return True


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


def _format_address(location: Dict[str, Any]) -> str:
    parts = [
        location.get("address_line_1"),
        location.get("address_line_2"),
        location.get("city"),
        location.get("county"),
        location.get("postcode"),
    ]
    cleaned = [str(part).strip() for part in parts if isinstance(part, str) and part.strip()]
    return ", ".join(cleaned)


def _extract_api_error(payload: Dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    data = payload.get("data")
    if isinstance(data, dict):
        nested_message = data.get("message")
        if isinstance(nested_message, str) and nested_message.strip():
            return nested_message.strip()

    error = payload.get("error")
    if isinstance(error, dict):
        details = error.get("details")
        if isinstance(details, str) and details.strip():
            return details.strip()
    return None


def _latest_iso(current_value: Optional[str], candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return current_value
    if not current_value:
        return candidate
    try:
        current_dt = datetime.fromisoformat(current_value.replace("Z", "+00:00"))
        candidate_dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return candidate or current_value
    return candidate if candidate_dt >= current_dt else current_value


def _extract_retry_after_seconds(response: Any) -> float:
    if response is None:
        return DEFAULT_429_BACKOFF_SECONDS

    retry_after = None
    headers = getattr(response, "headers", None)
    if headers is not None:
        retry_after = headers.get("Retry-After")

    if not retry_after:
        return DEFAULT_429_BACKOFF_SECONDS

    retry_after_text = str(retry_after).strip()
    if not retry_after_text:
        return DEFAULT_429_BACKOFF_SECONDS

    try:
        return max(float(retry_after_text), 0.5)
    except ValueError:
        pass

    try:
        target_time = parsedate_to_datetime(retry_after_text)
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        delay = (target_time - datetime.now(timezone.utc)).total_seconds()
        return max(delay, 0.5)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_429_BACKOFF_SECONDS


async def _parse_json_response(response) -> Dict[str, Any]:
    try:
        payload = await response.json(content_type=None)
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}
