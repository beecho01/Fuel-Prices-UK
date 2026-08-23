"""Sensor platform for the Fuel Prices UK integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_ADDRESS,
    ATTR_BRAND,
    ATTR_DISTANCE,
    ATTR_LAST_UPDATED,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_POSTCODE,
    ATTR_STATION_NAME,
    CONF_ADDRESS,
    CONF_CHEAPEST_COUNT,
    CONF_FUELTYPES,
    CONF_LOCATION,
    CONF_MAX_DATA_AGE_DAYS,
    CONF_NEAREST_COUNT,
    CONF_RADIUS,
    DEFAULT_CHEAPEST_COUNT,
    DEFAULT_MAX_DATA_AGE_DAYS,
    DEFAULT_NEAREST_COUNT,
    DOMAIN,
    ENTRY_TITLE,
    KM_TO_MILES,
    MAX_CHEAPEST_COUNT,
    MAX_NEAREST_COUNT,
    MIN_CHEAPEST_COUNT,
)
from .price_parser import coerce_price

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by UK Government Fuel Price open data scheme"


def _entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return merged config where options override data."""
    config = dict(entry.data)
    if entry.options:
        config.update(dict(entry.options))
    return config


def _base_attributes(fuel_type: str, price_rank: int) -> dict[str, Any]:
    return {
        ATTR_ATTRIBUTION: ATTRIBUTION,
        "fuel_type": fuel_type,
        "price_rank": price_rank,
        "price_rank_label": _ordinal(price_rank),
    }


def _ordinal(rank: int) -> str:
    suffix = "th" if rank % 100 in (11, 12, 13) else {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"


def _coerce_cheapest_count(value: Any, *, default_value: int) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default_value
    return max(MIN_CHEAPEST_COUNT, min(MAX_CHEAPEST_COUNT, count))


def _coerce_nearest_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = DEFAULT_NEAREST_COUNT
    return max(0, min(MAX_NEAREST_COUNT, count))


_LAST_UPDATED_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)


def _parse_last_updated(value: str | None) -> datetime | None:
    """Parse a last_updated string into an aware datetime, or return None."""
    if not value:
        return None
    for fmt in _LAST_UPDATED_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None


def _radius_to_miles(radius_km: Any) -> float:
    try:
        radius_value = float(radius_km)
    except (TypeError, ValueError):
        radius_value = 5.0
    return round(radius_value * KM_TO_MILES, 1)


def _derive_location_strings(entry: ConfigEntry) -> tuple[str, str]:
    entry_config = _entry_config(entry)
    radius_mi = _radius_to_miles(entry_config.get(CONF_RADIUS, 5))
    radius_text = f"{radius_mi:g} mi"

    address = entry_config.get(CONF_ADDRESS)
    if isinstance(address, str) and address.strip():
        base_label = address.strip()
    else:
        location = entry_config.get(CONF_LOCATION) or {}
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            base_label = f"{float(latitude):.4f},{float(longitude):.4f}"
        else:
            base_label = entry.title or ENTRY_TITLE

    location_label = f"{base_label} · {radius_text}"
    slug_source = f"{base_label} {radius_text}"
    location_slug = slugify(slug_source) or slugify(entry.entry_id) or "fuel_prices_uk"
    return location_label, location_slug


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    try:
        entry_config = _entry_config(entry)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        fuel_types: list[str] = entry_config.get(CONF_FUELTYPES, [])
        cheapest_count_raw = entry_config.get(CONF_CHEAPEST_COUNT)
        default_count = DEFAULT_CHEAPEST_COUNT if cheapest_count_raw is not None else 1
        cheapest_count = _coerce_cheapest_count(cheapest_count_raw, default_value=default_count)
        _LOGGER.info(
            "Setting up sensors for fuel types: %s (rank_count=%s)",
            fuel_types,
            cheapest_count,
        )

        if not fuel_types:
            _LOGGER.error("No fuel types configured in entry data")
            return

        entities: list[CheapestFuelPriceSensor] = [
            CheapestFuelPriceSensor(coordinator, entry, fuel_type, rank)
            for fuel_type in fuel_types
            for rank in range(1, cheapest_count + 1)
        ]

        nearest_count = _coerce_nearest_count(entry_config.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT))
        if nearest_count > 0:
            entities += [
                NearestFuelStationSensor(coordinator, entry, fuel_type, rank)
                for fuel_type in fuel_types
                for rank in range(1, nearest_count + 1)
            ]
            _LOGGER.info(
                "Adding nearest-by-distance sensors for fuel types: %s (count=%s)",
                fuel_types,
                nearest_count,
            )

        _LOGGER.info("Created %s fuel price sensors", len(entities))
        async_add_entities(entities, False)

    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.error("Failed to set up fuel price sensors: %s", err, exc_info=True)
        raise


class CheapestFuelPriceSensor(CoordinatorEntity, SensorEntity):  # type: ignore[misc]
    """Representation of a Cheapest Fuel Price Sensor."""

    def __init__(self, coordinator, entry: ConfigEntry, fuel_type: str, price_rank: int = 1) -> None:
        super().__init__(coordinator)
        self._fuel_type = fuel_type
        self._price_rank = max(1, int(price_rank))
        self._rank_label = _ordinal(self._price_rank)
        location_label, location_slug = _derive_location_strings(entry)
        fuel_slug = slugify(fuel_type) or fuel_type.lower()
        if self._price_rank == 1:
            # Keep legacy identifiers for the primary cheapest sensor.
            self.entity_id = f"sensor.fuel_price_uk_{location_slug}_cheapest_{fuel_slug}"
            self._attr_unique_id = f"{entry.entry_id}_{fuel_type}_cheapest"
            self._attr_name = f"{ENTRY_TITLE} ({location_label}) - Cheapest {fuel_type}"
        else:
            self.entity_id = f"sensor.fuel_price_uk_{location_slug}_rank_{self._price_rank}_cheapest_{fuel_slug}"
            self._attr_unique_id = f"{entry.entry_id}_{fuel_type}_cheapest_{self._price_rank}"
            self._attr_name = f"{ENTRY_TITLE} ({location_label}) - {self._rank_label} Cheapest {fuel_type}"
        self._location_label = location_label
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "GBP"
        self._attr_suggested_display_precision = 3
        self._attr_icon = "mdi:gas-station"
        self._station_data: dict[str, Any] | None = None
        self._attr_extra_state_attributes = _base_attributes(fuel_type, self._price_rank)
        self._attr_native_value = None
        self._attr_available = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.data is not None:
            self._refresh_snapshot()
            self.async_write_ha_state()

    def _refresh_snapshot(self) -> None:
        data = self.coordinator.data or []
        if not isinstance(data, list):
            self._station_data = None
            self._attr_native_value = None
            self._attr_extra_state_attributes = _base_attributes(self._fuel_type, self._price_rank)
            self._attr_available = False
            _LOGGER.debug(
                "[sensor][%s][rank=%s] Coordinator payload type %s is not list-like; sensor unavailable",
                self._fuel_type,
                self._price_rank,
                type(self.coordinator.data).__name__,
            )
            return

        total_stations = len(data)
        price_candidates = 0
        price_matches = 0
        ranked_candidates: list[tuple[float, dict[str, Any]]] = []

        entry_config = _entry_config(self.coordinator.entry)
        max_data_age_days = int(entry_config.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS))
        staleness_cutoff: datetime | None = None
        if max_data_age_days > 0:
            staleness_cutoff = datetime.now(UTC) - timedelta(days=max_data_age_days)

        for station in data:
            if not isinstance(station, dict):
                continue

            prices = station.get("prices")
            if not isinstance(prices, dict):
                continue

            price_entry = prices.get(self._fuel_type)
            price_value = coerce_price(price_entry)
            price_candidates += 1
            if price_value is None:
                continue

            if staleness_cutoff is not None and isinstance(price_entry, dict):
                lu_raw = price_entry.get("last_updated") or price_entry.get("timestamp")
                lu_dt = _parse_last_updated(lu_raw)
                if lu_dt is not None and lu_dt < staleness_cutoff:
                    _LOGGER.debug(
                        "[sensor][%s][rank=%s] Skipping stale price for station %s (last_updated=%s)",
                        self._fuel_type,
                        self._price_rank,
                        station.get("site_id"),
                        lu_raw,
                    )
                    continue

            price_matches += 1
            ranked_candidates.append((price_value, station))

        ranked_candidates.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("site_id") or item[1].get("id") or ""),
            )
        )

        selected_price: float | None = None
        selected_station: dict[str, Any] | None = None
        if len(ranked_candidates) >= self._price_rank:
            selected_price, selected_station = ranked_candidates[self._price_rank - 1]

        self._station_data = selected_station if isinstance(selected_station, dict) else None
        self._attr_native_value = selected_price
        self._rebuild_attributes()
        self._attr_available = bool(self.coordinator.last_update_success and selected_price is not None)

        if selected_price is None:
            if total_stations == 0:
                _LOGGER.warning(
                    "[sensor][%s][%s] Coordinator returned no stations; sensor state remains unknown",
                    self._fuel_type,
                    self._rank_label,
                )
            elif price_matches == 0:
                _LOGGER.warning(
                    "[sensor][%s][%s] Checked %s stations (%s price entries) but none exposed %s pricing",
                    self._fuel_type,
                    self._rank_label,
                    total_stations,
                    price_candidates,
                    self._fuel_type,
                )
            else:
                _LOGGER.debug(
                    "[sensor][%s][%s] Coordinator updated; ranked prices available=%s but requested rank was missing",
                    self._fuel_type,
                    self._rank_label,
                    price_matches,
                )
        else:
            _LOGGER.debug(
                "[sensor][%s][%s] Price=%.3f from station=%s (stations=%s candidates=%s matches=%s)",
                self._fuel_type,
                self._rank_label,
                selected_price,
                self._station_data.get("site_id") if self._station_data else "<unknown>",
                total_stations,
                price_candidates,
                price_matches,
            )

    def _rebuild_attributes(self) -> None:
        attributes = _base_attributes(self._fuel_type, self._price_rank)
        station = self._station_data
        if not station or not isinstance(station, dict):
            self._attr_extra_state_attributes = attributes
            return

        if station.get("name"):
            attributes[ATTR_STATION_NAME] = station["name"]

        location = station.get("location") if isinstance(station.get("location"), dict) else None
        address = station.get("address")
        if not address and location:
            address_parts = [
                part
                for part in (
                    location.get("address"),
                    location.get("town"),
                    location.get("postcode"),
                )
                if part
            ]
            address = ", ".join(address_parts) if address_parts else None
        if address:
            attributes[ATTR_ADDRESS] = address

        postcode = station.get("postcode")
        if not postcode and location:
            postcode = location.get("postcode")
        if postcode:
            attributes[ATTR_POSTCODE] = postcode

        lat = station.get("latitude") or (location.get("latitude") if location else None)
        lon = station.get("longitude") or (location.get("longitude") if location else None)
        if lat is not None:
            attributes[ATTR_LATITUDE] = lat
        if lon is not None:
            attributes[ATTR_LONGITUDE] = lon

        brand = station.get("brand") or station.get("retailer")
        if brand:
            attributes[ATTR_BRAND] = brand

        distance_value = station.get("distance")
        if isinstance(distance_value, (int, float)):
            attributes[ATTR_DISTANCE] = round(distance_value * KM_TO_MILES, 2)

        prices: dict[str, Any] = {}
        station_prices = station.get("prices")
        if isinstance(station_prices, dict):
            prices = station_prices

        price_meta = prices.get(self._fuel_type)
        if isinstance(price_meta, dict):
            last_updated = price_meta.get("last_updated") or price_meta.get("timestamp")
            if last_updated:
                attributes[ATTR_LAST_UPDATED] = last_updated
        elif station.get("last_updated"):
            attributes[ATTR_LAST_UPDATED] = station["last_updated"]

        self._attr_extra_state_attributes = attributes

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_snapshot()
        super()._handle_coordinator_update()


class NearestFuelStationSensor(CheapestFuelPriceSensor):
    """Sensor showing the price at the Nth nearest station for a given fuel type."""

    def __init__(
        self,
        coordinator: Any,
        entry: ConfigEntry,
        fuel_type: str,
        nearest_rank: int = 1,
    ) -> None:
        """Initialise with distance-based naming and unique ID."""
        super().__init__(coordinator, entry, fuel_type, nearest_rank)
        location_label, location_slug = _derive_location_strings(entry)
        fuel_slug = slugify(fuel_type) or fuel_type.lower()
        rank_label = _ordinal(nearest_rank)
        self.entity_id = f"sensor.fuel_price_uk_{location_slug}_nearest_{nearest_rank}_{fuel_slug}"
        self._attr_unique_id = f"{entry.entry_id}_{fuel_type}_nearest_{nearest_rank}"
        self._attr_name = f"{ENTRY_TITLE} ({location_label}) - {rank_label} Nearest {fuel_type}"
        self._rank_label = rank_label

    def _refresh_snapshot(self) -> None:
        data = self.coordinator.data or []
        if not isinstance(data, list):
            self._station_data = None
            self._attr_native_value = None
            self._attr_extra_state_attributes = _base_attributes(self._fuel_type, self._price_rank)
            self._attr_available = False
            return

        entry_config = _entry_config(self.coordinator.entry)
        max_data_age_days = int(entry_config.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS))
        staleness_cutoff: datetime | None = None
        if max_data_age_days > 0:
            staleness_cutoff = datetime.now(UTC) - timedelta(days=max_data_age_days)

        # Collect stations with a valid price for this fuel type, sorted by distance
        distance_candidates: list[tuple[float, dict[str, Any]]] = []
        for station in data:
            if not isinstance(station, dict):
                continue
            prices = station.get("prices")
            if not isinstance(prices, dict):
                continue
            price_entry = prices.get(self._fuel_type)
            if coerce_price(price_entry) is None:
                continue
            if staleness_cutoff is not None and isinstance(price_entry, dict):
                lu_raw = price_entry.get("last_updated") or price_entry.get("timestamp")
                lu_dt = _parse_last_updated(lu_raw)
                if lu_dt is not None and lu_dt < staleness_cutoff:
                    continue
            dist = station.get("distance")
            if not isinstance(dist, (int, float)):
                continue
            distance_candidates.append((dist, station))

        # Sort by distance ascending, then by site_id for stability
        distance_candidates.sort(key=lambda item: (item[0], str(item[1].get("site_id") or "")))

        selected_price: float | None = None
        selected_station: dict[str, Any] | None = None
        if len(distance_candidates) >= self._price_rank:
            _, selected_station = distance_candidates[self._price_rank - 1]
            selected_price = coerce_price(selected_station.get("prices", {}).get(self._fuel_type))

        self._station_data = selected_station if isinstance(selected_station, dict) else None
        self._attr_native_value = selected_price
        self._rebuild_attributes()
        self._attr_available = bool(self.coordinator.last_update_success and selected_price is not None)

        _LOGGER.debug(
            "[sensor][nearest][%s][rank=%s] selected station=%s dist=%.3f mi price=%s",
            self._fuel_type,
            self._price_rank,
            self._station_data.get("site_id") if self._station_data else "<none>",
            (self._station_data.get("distance", 0) * KM_TO_MILES) if self._station_data else 0,
            selected_price,
        )

    def _rebuild_attributes(self) -> None:
        """Build attributes using distance_rank instead of price_rank."""
        super()._rebuild_attributes()
        attrs = dict(self._attr_extra_state_attributes)
        price_rank = attrs.pop("price_rank", None)
        price_rank_label = attrs.pop("price_rank_label", None)
        if price_rank is not None:
            attrs["distance_rank"] = price_rank
        if price_rank_label is not None:
            attrs["distance_rank_label"] = price_rank_label
        self._attr_extra_state_attributes = attrs
