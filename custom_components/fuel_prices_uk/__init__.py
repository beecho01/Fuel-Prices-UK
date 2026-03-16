"""The Fuel Prices UK integration."""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List, Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_UPDATE_INTERVAL,
    CONF_STATIONS,
    CONF_FUELTYPES,
    ENTRY_TITLE,
    CONF_LOCATION,
    CONF_RADIUS,
)
from .api_client import FuelPricesAPI
from .fetch_prices import fetch_stations_by_criteria

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, _config: Mapping[str, Any]) -> bool:
    """Set up the Fuel Prices UK integration."""
    # We don't support YAML-based configuration, so return True
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Fuel Prices UK from a config entry."""
    _LOGGER.info("Setting up Fuel Prices UK config entry: %s", entry.entry_id)
    _LOGGER.debug("Entry data: %s", _redacted_entry_data(entry.data))

    hass.data.setdefault(DOMAIN, {})
    domain_data = hass.data[DOMAIN]

    client_id = str(entry.data.get(CONF_CLIENT_ID, "")).strip()
    client_secret = str(entry.data.get(CONF_CLIENT_SECRET, "")).strip()
    if not client_id or not client_secret:
        raise ConfigEntryNotReady(
            "Fuel Finder API credentials are missing. Reconfigure the integration with a valid client ID and secret."
        )

    api_client = FuelPricesAPI(
        hass,
        client_id=client_id,
        client_secret=client_secret,
    )

    update_interval = timedelta(seconds=entry.data[CONF_UPDATE_INTERVAL])
    _LOGGER.info("Update interval set to: %s", update_interval)

    coordinator = FuelPricesDataUpdateCoordinator(
        hass,
        entry=entry,
        update_interval=update_interval,
        api_client=api_client,
    )

    domain_data[entry.entry_id] = coordinator

    # Use the updated method
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener to reload on options change
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Perform first refresh in the background so setup is not blocked by slow API paging.
    coordinator.start_startup_refresh()

    _LOGGER.info("Successfully set up Fuel Prices UK integration")
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry: %s", entry.entry_id)
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if isinstance(coordinator, FuelPricesDataUpdateCoordinator):
        coordinator.cancel_startup_refresh()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class FuelPricesDataUpdateCoordinator(DataUpdateCoordinator[List[Dict[str, Any]]]):
    """Class to manage fetching data from the Fuel Prices UK sources."""

    def __init__(self, hass, entry: ConfigEntry, update_interval: timedelta, api_client: FuelPricesAPI):
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.stations = entry.data.get(CONF_STATIONS, [])
        self.location = entry.data.get(CONF_LOCATION)
        self.radius = entry.data.get(CONF_RADIUS, 5)
        self.fuel_types = entry.data.get(CONF_FUELTYPES, ["E10", "B7"])
        self.update_interval = update_interval
        self._logger = _LOGGER
        self.api_client = api_client
        self._startup_refresh_task: asyncio.Task[None] | None = None

        _LOGGER.info(
            "[coordinator][__init__] Initialising with location=%s, radius=%s km, fuel_types=%s, update_interval=%s",
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

    def start_startup_refresh(self) -> None:
        """Kick off one startup refresh without blocking config entry setup."""
        if self._startup_refresh_task and not self._startup_refresh_task.done():
            return

        self._startup_refresh_task = self.hass.async_create_task(
            self._async_run_startup_refresh(),
            name=f"{DOMAIN}_{self.entry.entry_id}_startup_refresh",
        )

    def cancel_startup_refresh(self) -> None:
        """Cancel startup refresh task if it is still running."""
        if self._startup_refresh_task and not self._startup_refresh_task.done():
            self._startup_refresh_task.cancel()

    async def _async_run_startup_refresh(self) -> None:
        """Run first refresh in background so entities can appear immediately."""
        _LOGGER.info("[coordinator][startup_refresh] Starting background initial refresh")
        try:
            initial_success = await self._async_run_startup_refresh_attempt("initial")
            if initial_success:
                _LOGGER.info("[coordinator][startup_refresh] Initial refresh completed successfully")
                return

            _LOGGER.warning(
                "[coordinator][startup_refresh] Initial refresh was unsuccessful; triggering immediate retry"
            )
            retry_success = await self._async_run_startup_refresh_attempt("retry")
            if retry_success:
                _LOGGER.info("[coordinator][startup_refresh] Immediate retry completed successfully")
            else:
                _LOGGER.warning(
                    "[coordinator][startup_refresh] Immediate retry was also unsuccessful; waiting for scheduled refresh"
                )
        except asyncio.CancelledError:
            _LOGGER.debug("[coordinator][startup_refresh] Background initial refresh cancelled")
            raise
        finally:
            self._startup_refresh_task = None

    async def _async_run_startup_refresh_attempt(self, phase: str) -> bool:
        """Execute one startup refresh attempt and report whether coordinator data update succeeded."""
        try:
            await self.async_refresh()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # pragma: no cover - defensive; async_refresh usually handles failures
            _LOGGER.error(
                "[coordinator][startup_refresh] %s attempt raised unexpected exception: %s",
                phase,
                err,
                exc_info=True,
            )
            return False

        return bool(self.last_update_success)

    async def _async_update_data(self) -> List[Dict[str, Any]]:
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
                    self.api_client,
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
                        station_data = await fetch_stations_by_criteria(
                            self.api_client,
                            site_id=site_id
                        )
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

        except asyncio.CancelledError:
            _LOGGER.debug("[coordinator][_async_update_data] Update cycle cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Error fetching data: %s", err, exc_info=True)
            raise UpdateFailed(f"Error fetching data: {err}") from err


def _redacted_entry_data(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Return config entry data with sensitive fields masked for logging."""
    safe = dict(data)
    if CONF_CLIENT_SECRET in safe and safe[CONF_CLIENT_SECRET]:
        safe[CONF_CLIENT_SECRET] = "***REDACTED***"
    return safe