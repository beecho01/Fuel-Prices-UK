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
    CONF_LOCATION,
    CONF_RADIUS,
)
from .fetch_prices import fetch_stations_by_criteria

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Fuel Prices UK integration."""
    # We don't support YAML-based configuration, so return True
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Fuel Prices UK from a config entry."""
    _LOGGER.info("Setting up Fuel Prices UK config entry: %s", entry.entry_id)
    _LOGGER.debug("Entry data: %s", entry.data)

    update_interval = timedelta(seconds=entry.data[CONF_UPDATE_INTERVAL])
    _LOGGER.info("Update interval set to: %s", update_interval)

    coordinator = FuelPricesDataUpdateCoordinator(
        hass, entry=entry, update_interval=update_interval
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Failed to fetch initial data: %s", err, exc_info=True)
        raise ConfigEntryNotReady(f"Failed to fetch initial fuel price data: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Use the updated method
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener to reload on options change
    entry.async_on_unload(entry.add_update_listener(update_listener))

    _LOGGER.info("Successfully set up Fuel Prices UK integration")
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


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
        self.stations = entry.data.get(CONF_STATIONS, [])
        self.location = entry.data.get(CONF_LOCATION)
        self.radius = entry.data.get(CONF_RADIUS, 5)
        self.fuel_types = entry.data.get(CONF_FUELTYPES, ["E10", "B7"])
        self.update_interval = update_interval
        self._logger = _LOGGER

        _LOGGER.info(
            "[coordinator][__init__] Initializing with location=%s, radius=%s km, fuel_types=%s, update_interval=%s",
            self.location, self.radius, self.fuel_types, update_interval
        )

        super().__init__(
            hass,
            _LOGGER,
            name=ENTRY_TITLE,
            config_entry=entry,
            update_interval=update_interval,
            always_update=False,  # Only update if data changes to avoid unnecessary state writes
        )

    async def _async_update_data(self):  # type: ignore[override]
        """Fetch data from fuel price sources."""
        try:
            _LOGGER.info("[coordinator][_async_update_data] Starting data update cycle")
            
            # Determine search criteria based on configuration
            latitude = self.location.get("latitude") if self.location else None
            longitude = self.location.get("longitude") if self.location else None
            
            _LOGGER.info("[coordinator][_async_update_data] Search coordinates: lat=%s, lon=%s", latitude, longitude)
            _LOGGER.info("[coordinator][_async_update_data] Fuel types to search: %s", self.fuel_types)
            
            # Fetch stations based on criteria
            if latitude and longitude:
                # Radius-based search
                _LOGGER.info(
                    "[coordinator][_async_update_data] Performing radius-based search: lat=%s, lon=%s, radius=%s km",
                    latitude, longitude, self.radius
                )
                stations_data = await fetch_stations_by_criteria(
                    latitude=latitude,
                    longitude=longitude,
                    radius_km=self.radius,
                    fuel_types=self.fuel_types
                )
            elif self.stations and len(self.stations) > 0:
                # Specific station search
                _LOGGER.debug("Performing specific station search for %s stations", len(self.stations))
                stations_data = []
                for station_config in self.stations:
                    site_id = station_config.get("site_id")
                    if site_id:
                        _LOGGER.debug("Fetching station with site_id: %s", site_id)
                        station_data = await fetch_stations_by_criteria(site_id=site_id)
                        if station_data:
                            _LOGGER.debug("Found station data for site_id: %s", site_id)
                            stations_data.extend(station_data)
                        else:
                            _LOGGER.warning("No data found for site_id: %s", site_id)
            else:
                _LOGGER.warning("No valid search criteria in configuration")
                return []
            
            _LOGGER.info("Successfully fetched %s stations", len(stations_data))
            _LOGGER.debug("Station data: %s", stations_data[:2] if len(stations_data) > 2 else stations_data)
            return stations_data
            
        except Exception as err:
            _LOGGER.error("Error fetching data: %s", err, exc_info=True)
            raise UpdateFailed(f"Error fetching data: {err}") from err