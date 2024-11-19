"""The Fuel Prices UK integration."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    SCHEMA_VERSION,
    CONF_UPDATE_INTERVAL,
    CONF_STATIONS,
    CONF_FUELTYPES,
    NAME,
    INTEGRATION_ID,
    ENTRY_TITLE,
)
from .fetch_prices import get_all_prices

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Fuel Prices UK integration."""
    # We don't support YAML-based configuration, so return True
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Fuel Prices UK from a config entry."""
    _LOGGER.debug("Setting up config entry: %s", entry.entry_id)

    update_interval = timedelta(seconds=entry.data[CONF_UPDATE_INTERVAL])

    coordinator = FuelPricesDataUpdateCoordinator(
        hass, entry=entry, update_interval=update_interval
    )

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Use the updated method
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class FuelPricesDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Fuel Prices UK sources."""

    def __init__(self, hass, entry: ConfigEntry, update_interval: timedelta):
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.stations = entry.data[CONF_STATIONS]
        self.update_interval = update_interval
        self._logger = _LOGGER

        super().__init__(
            hass,
            _LOGGER,
            name=ENTRY_TITLE,
            update_interval=update_interval,
        )

    async def _async_update_data(self):
        """Fetch data from fuel price sources."""
        try:
            # Run the data fetching in an executor to avoid blocking the event loop
            data = await self.hass.async_add_executor_job(self.fetch_data)
            return data
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    def fetch_data(self):
        """Fetch data synchronously."""
        self._logger.debug("Fetching fuel price data...")
        # Fetch all prices
        all_prices = get_all_prices()

        # You can process and filter the data here based on selected stations and fuel types
        filtered_data = self.filter_data(all_prices)
        return filtered_data

    def filter_data(self, all_prices):
        """Filter data based on user configuration."""
        filtered_data = []
        selected_stations = [station[NAME] for station in self.stations]

        for retailer in all_prices:
            if retailer["retailer"] in selected_stations:
                # Find the station configuration
                station_config = next(
                    (s for s in self.stations if s[NAME] == retailer["retailer"]), None
                )
                if station_config:
                    # Filter fuel types
                    fuel_types = station_config[CONF_FUELTYPES]
                    # Process data as needed
                    retailer_data = {
                        "retailer": retailer["retailer"],
                        "data": retailer["data"],
                        "fuel_types": fuel_types,
                    }
                    filtered_data.append(retailer_data)
        return filtered_data