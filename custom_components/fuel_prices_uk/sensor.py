"""Sensor platform for the Fuel Prices UK integration."""
import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    NAME,
    ATTR_LAST_UPDATED,
    ATTR_RETAILER,
    ATTR_FUEL_TYPES,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for retailer_data in coordinator.data:
        retailer_name = retailer_data["name"]
        fuel_types = retailer_data["fuel_types"]
        stations = retailer_data["data"].get("stations", [])
        
        for station in stations:
            station_name = station.get("name", "Unknown Station")
            station_id = station.get("id", None)
            if not station_id:
                continue  # Skip stations without an ID

            for fuel_type in fuel_types:
                sensor = FuelPriceSensor(
                    coordinator,
                    retailer_name,
                    station_name,
                    station_id,
                    fuel_type,
                )
                entities.append(sensor)

    async_add_entities(entities)


class FuelPriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Fuel Price Sensor."""

    def __init__(self, coordinator, retailer_name, station_name, station_id, fuel_type):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.retailer_name = retailer_name
        self.station_name = station_name
        self.station_id = station_id
        self.fuel_type = fuel_type
        self._attr_name = f"{retailer_name} {station_name} {fuel_type}"
        self._attr_unique_id = f"{retailer_name}_{station_id}_{fuel_type}"
        self._state = None
        self._last_updated = None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "GBP"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        return {
            ATTR_LAST_UPDATED: self._last_updated,
            ATTR_RETAILER: self.retailer_name,
            "station_name": self.station_name,
            "fuel_type": self.fuel_type,
        }

    async def async_update(self):
        """Update the sensor state."""
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        for retailer_data in self.coordinator.data:
            if retailer_data["name"] != self.retailer_name:
                continue
            stations = retailer_data["data"].get("stations", [])
            for station in stations:
                if station.get("id") != self.station_id:
                    continue
                prices = station.get("prices", {})
                price_info = prices.get(self.fuel_type)
                if price_info:
                    self._state = price_info.get("price")
                    self._last_updated = price_info.get("last_updated")
                else:
                    self._state = None
                    self._last_updated = None
        self.async_write_ha_state()