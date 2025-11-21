"""Sensor platform for the Fuel Prices UK integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ADDRESS,
    ATTR_BRAND,
    ATTR_DISTANCE,
    ATTR_LATITUDE,
    ATTR_LAST_UPDATED,
    ATTR_LONGITUDE,
    ATTR_POSTCODE,
    ATTR_STATION_NAME,
    CONF_FUELTYPES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by UK Government Fuel Price open data scheme"
from .price_parser import coerce_price


def _base_attributes(fuel_type: str) -> Dict[str, Any]:
    return {
        ATTR_ATTRIBUTION: ATTRIBUTION,
        "fuel_type": fuel_type,
    }


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        fuel_types: List[str] = entry.data.get(CONF_FUELTYPES, [])
        _LOGGER.info("Setting up sensors for fuel types: %s", fuel_types)

        if not fuel_types:
            _LOGGER.error("No fuel types configured in entry data")
            return

        entities = [
            CheapestFuelPriceSensor(coordinator, fuel_type, entry.entry_id)
            for fuel_type in fuel_types
        ]

        _LOGGER.info("Created %s fuel price sensors", len(entities))
        async_add_entities(entities, True)

    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.error("Failed to set up fuel price sensors: %s", err, exc_info=True)
        raise


class CheapestFuelPriceSensor(CoordinatorEntity, SensorEntity):  # type: ignore[misc]
    """Representation of a Cheapest Fuel Price Sensor."""

    def __init__(self, coordinator, fuel_type: str, entry_id: str) -> None:
        super().__init__(coordinator)
        self._fuel_type = fuel_type
        self._attr_name = f"Cheapest {fuel_type} Price"
        self._attr_unique_id = f"{entry_id}_{fuel_type}_cheapest"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "GBP"
        self._attr_suggested_display_precision = 3
        self._attr_icon = "mdi:gas-station"
        self._station_data: Optional[Dict[str, Any]] = None
        self._attr_extra_state_attributes = _base_attributes(fuel_type)
        self._attr_native_value = None
        self._attr_available = False

    def _refresh_snapshot(self) -> None:
        data = self.coordinator.data or []
        if not isinstance(data, list):
            self._station_data = None
            self._attr_native_value = None
            self._attr_extra_state_attributes = _base_attributes(self._fuel_type)
            self._attr_available = False
            _LOGGER.debug(
                "[sensor][%s] Coordinator payload type %s is not list-like; sensor unavailable",
                self._fuel_type,
                type(self.coordinator.data).__name__,
            )
            return

        total_stations = len(data)
        price_candidates = 0
        price_matches = 0
        cheapest_price: Optional[float] = None
        cheapest_station: Optional[Dict[str, Any]] = None

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

            price_matches += 1
            if cheapest_price is None or price_value < cheapest_price:
                cheapest_price = price_value
                cheapest_station = station

        self._station_data = cheapest_station if isinstance(cheapest_station, dict) else None
        self._attr_native_value = cheapest_price
        self._rebuild_attributes()
        self._attr_available = bool(self.coordinator.last_update_success and cheapest_price is not None)

        if cheapest_price is None:
            if total_stations == 0:
                _LOGGER.warning(
                    "[sensor][%s] Coordinator returned no stations; sensor state remains unknown",
                    self._fuel_type,
                )
            elif price_matches == 0:
                _LOGGER.warning(
                    "[sensor][%s] Checked %s stations (%s price entries) but none exposed %s pricing",
                    self._fuel_type,
                    total_stations,
                    price_candidates,
                    self._fuel_type,
                )
            else:
                _LOGGER.debug(
                    "[sensor][%s] Coordinator updated; price comparisons made=%s but no cheapest result",
                    self._fuel_type,
                    price_matches,
                )
        else:
            _LOGGER.debug(
                "[sensor][%s] Cheapest price=%.3f from station=%s (stations=%s candidates=%s matches=%s)",
                self._fuel_type,
                cheapest_price,
                self._station_data.get("site_id") if self._station_data else "<unknown>",
                total_stations,
                price_candidates,
                price_matches,
            )

    def _rebuild_attributes(self) -> None:
        attributes = _base_attributes(self._fuel_type)
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
            attributes[ATTR_DISTANCE] = round(distance_value, 2)

        prices: Dict[str, Any] = {}
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
