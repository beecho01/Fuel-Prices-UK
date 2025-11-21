"""Sensor platform for the Fuel Prices UK integration."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass  # type: ignore[import-not-found]
from homeassistant.const import ATTR_ATTRIBUTION, CURRENCY_POUND  # type: ignore[import-not-found]
from homeassistant.helpers.update_coordinator import CoordinatorEntity  # type: ignore[import-not-found]
from homeassistant.core import callback  # type: ignore[import-not-found]

from .const import (
    DOMAIN,
    ATTR_LAST_UPDATED,
    ATTR_STATION_NAME,
    ATTR_ADDRESS,
    ATTR_POSTCODE,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_BRAND,
    ATTR_DISTANCE,
    CONF_FUELTYPES,
)

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by UK Government Fuel Price API"


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        
        # Get configured fuel types
        fuel_types = entry.data.get(CONF_FUELTYPES, [])
        _LOGGER.info("Setting up sensors for fuel types: %s", fuel_types)
        
        if not fuel_types:
            _LOGGER.error("No fuel types configured in entry data")
            return
        
        entities = []
        
        # We'll create sensors dynamically based on the data returned
        # For now, create one sensor per fuel type that will show the cheapest price
        for fuel_type in fuel_types:
            _LOGGER.debug("Creating sensor for fuel type: %s", fuel_type)
            entities.append(
                CheapestFuelPriceSensor(
                    coordinator,
                    fuel_type,
                    entry.entry_id
                )
            )
        
        _LOGGER.info("Created %s fuel price sensors", len(entities))
        async_add_entities(entities, True)
        
    except Exception as err:
        _LOGGER.error("Failed to set up fuel price sensors: %s", err, exc_info=True)
        raise


class CheapestFuelPriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Cheapest Fuel Price Sensor."""

    def __init__(self, coordinator, fuel_type: str, entry_id: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._fuel_type = fuel_type
        self._entry_id = entry_id
        self._attr_name = f"Cheapest {fuel_type} Price"
        self._attr_unique_id = f"{entry_id}_{fuel_type}_cheapest"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "GBP"  # ISO 4217 currency code
        self._attr_suggested_display_precision = 3  # Show 3 decimal places (e.g., 1.349)
        self._attr_icon = "mdi:gas-station"
        self._station_data: Optional[Dict[str, Any]] = None

    @property
    def native_value(self) -> Optional[float]:  # type: ignore[override]
        """Return the state of the sensor."""
        if not self.coordinator.data:
            _LOGGER.debug("No coordinator data available for %s sensor", self._fuel_type)
            return None
        
        _LOGGER.debug("Processing %s stations for %s sensor", len(self.coordinator.data), self._fuel_type)
        
        # Find the cheapest station with this fuel type
        cheapest_price = None
        cheapest_station = None
        
        for station in self.coordinator.data:
            prices = station.get("prices", {}) # type: ignore
            
            # Ensure prices is a dict
            if not isinstance(prices, dict):
                continue
            
            # Handle different possible price structures
            price = None
            if self._fuel_type in prices:
                price_data = prices[self._fuel_type]
                if isinstance(price_data, dict):
                    price = price_data.get("price")
                elif isinstance(price_data, (int, float)):
                    price = price_data
            
            if price is not None:
                # Convert pence to pounds if necessary
                if price > 100:  # Assume values > 100 are in pence
                    price = price / 100
                
                if cheapest_price is None or price < cheapest_price:
                    cheapest_price = price
                    cheapest_station = station
                    _LOGGER.debug(
                        "New cheapest %s: £%.2f at %s",
                        self._fuel_type, price, 
                        station.get('name', 'Unknown') if isinstance(station, dict) else 'Unknown'  # type: ignore[union-attr]
                    )
        
        self._station_data = cheapest_station if isinstance(cheapest_station, dict) else None
        
        if cheapest_price is not None:
            _LOGGER.info(
                "Cheapest %s: £%.2f at %s",
                self._fuel_type, cheapest_price, 
                self._station_data.get('name', 'Unknown') if self._station_data else 'Unknown'
            )
        else:
            _LOGGER.warning("No price found for fuel type: %s", self._fuel_type)
        
        return cheapest_price

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:  # type: ignore[misc]
        """Return extra attributes."""
        if not self._station_data:
            return {
                ATTR_ATTRIBUTION: ATTRIBUTION,
                "fuel_type": self._fuel_type,
            }
        
        # Type guard - ensure station_data is a dict
        if not isinstance(self._station_data, dict):
            return {
                ATTR_ATTRIBUTION: ATTRIBUTION,
                "fuel_type": self._fuel_type,
            }
        
        attributes = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "fuel_type": self._fuel_type,
        }
        
        # Add station information
        if "name" in self._station_data:
            attributes[ATTR_STATION_NAME] = self._station_data["name"]
        
        if "address" in self._station_data:
            attributes[ATTR_ADDRESS] = self._station_data["address"]
        elif "location" in self._station_data:
            # Sometimes address is nested in location
            location = self._station_data["location"]
            if isinstance(location, dict):
                address_parts = []
                if "address" in location:
                    address_parts.append(location["address"])
                if "town" in location:
                    address_parts.append(location["town"])
                if "postcode" in location:
                    address_parts.append(location["postcode"])
                if address_parts:
                    attributes[ATTR_ADDRESS] = ", ".join(address_parts)
        
        if "postcode" in self._station_data:
            attributes[ATTR_POSTCODE] = self._station_data["postcode"]
        elif "location" in self._station_data and isinstance(self._station_data["location"], dict):
            if "postcode" in self._station_data["location"]:
                attributes[ATTR_POSTCODE] = self._station_data["location"]["postcode"]
        
        if "latitude" in self._station_data:
            attributes[ATTR_LATITUDE] = self._station_data["latitude"]
        elif "location" in self._station_data and isinstance(self._station_data["location"], dict):
            if "latitude" in self._station_data["location"]:
                attributes[ATTR_LATITUDE] = self._station_data["location"]["latitude"]
        
        if "longitude" in self._station_data:
            attributes[ATTR_LONGITUDE] = self._station_data["longitude"]
        elif "location" in self._station_data and isinstance(self._station_data["location"], dict):
            if "longitude" in self._station_data["location"]:
                attributes[ATTR_LONGITUDE] = self._station_data["location"]["longitude"]
        
        if "brand" in self._station_data:
            attributes[ATTR_BRAND] = self._station_data["brand"]
        elif "retailer" in self._station_data:
            attributes[ATTR_BRAND] = self._station_data["retailer"]
        
        if "distance" in self._station_data:
            attributes[ATTR_DISTANCE] = round(self._station_data["distance"], 2)
        
        # Add last updated timestamp
        prices = self._station_data.get("prices", {})
        if self._fuel_type in prices:
            price_data = prices[self._fuel_type]
            if isinstance(price_data, dict) and "last_updated" in price_data:
                attributes[ATTR_LAST_UPDATED] = price_data["last_updated"]
        
        if "last_updated" in self._station_data:
            attributes[ATTR_LAST_UPDATED] = self._station_data["last_updated"]
        
        return attributes

    @property
    def available(self) -> bool:  # type: ignore[override]
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.native_value is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
