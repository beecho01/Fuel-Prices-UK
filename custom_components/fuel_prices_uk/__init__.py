"""The Fuel Prices UK integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.issue_registry as ir
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api_client import FuelPricesAPI
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_TRACKER,
    CONF_FUELTYPES,
    CONF_LOCATION,
    CONF_LOCATION_METHOD,
    CONF_RADIUS,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    CONSECUTIVE_FAILURE_THRESHOLD,
    DEFAULT_CHEAPEST_COUNT,
    DEFAULT_MAX_DATA_AGE_DAYS,
    DEFAULT_NEAREST_COUNT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENTRY_TITLE,
    FUEL_TYPE_B7,
    FUEL_TYPE_E5,
    FUEL_TYPE_E10,
    FUEL_TYPE_SDV,
    MAX_CHEAPEST_COUNT,
    MAX_NEAREST_COUNT,
    MIN_CHEAPEST_COUNT,
)
from .fetch_prices import fetch_stations_by_criteria

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

_INSTANCE_SCHEMA = vol.Schema(
    {
        # Optional name — required when configuring multiple locations so each
        # entry can be told apart.  Becomes the config entry title.
        vol.Optional("name"): cv.string,
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_CLIENT_SECRET): cv.string,
        # Location block — include exactly one of: postcode, address, or lat+long.
        # Omit the entire block to use HA's configured home location.
        vol.Optional("location"): vol.Schema(
            {
                vol.Optional("postcode"): cv.string,
                vol.Optional("address"): cv.string,
                vol.Optional("lat"): cv.latitude,
                vol.Optional("long"): cv.longitude,
            }
        ),
        # Radius with explicit unit
        vol.Optional("radius"): vol.Schema(
            {
                vol.Required("type"): vol.In(["miles", "km"]),
                vol.Required("value"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=200)),
            }
        ),
        # Fuel types as a boolean map; omit to default to E10 + B7
        vol.Optional("fuel_types"): vol.Schema(
            {
                vol.Optional(FUEL_TYPE_E10): cv.boolean,
                vol.Optional(FUEL_TYPE_E5): cv.boolean,
                vol.Optional(FUEL_TYPE_B7): cv.boolean,
                vol.Optional(FUEL_TYPE_SDV): cv.boolean,
            }
        ),
        # Sensor count options
        vol.Optional("count"): vol.Schema(
            {
                vol.Optional("cheapest", default=DEFAULT_CHEAPEST_COUNT): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT),
                ),
                vol.Optional("nearest", default=DEFAULT_NEAREST_COUNT): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)
                ),
            }
        ),
        vol.Optional("ignore_stale_data_days", default=DEFAULT_MAX_DATA_AGE_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=30)
        ),
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=300, max=86400)
        ),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        # Accept either a single mapping or a list of mappings so users can
        # configure multiple locations under the same domain key.
        DOMAIN: vol.All(cv.ensure_list, [_INSTANCE_SCHEMA])
    },
    extra=vol.ALLOW_EXTRA,
)


def _entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return merged config where options override data."""
    config = dict(entry.data)
    if entry.options:
        config.update(dict(entry.options))
    return config


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Fuel Prices UK integration, importing YAML config if present."""
    hass.data.setdefault(DOMAIN, {})
    instances = config.get(DOMAIN, [])
    if instances:
        _LOGGER.info(
            "Detected %d fuel_prices_uk YAML instance(s) — importing as config "
            "entries. Consider removing the YAML block(s) once entries are created.",
            len(instances),
        )
        for instance in instances:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data=dict(instance),
                )
            )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Fuel Prices UK from a config entry."""
    _LOGGER.info("Setting up Fuel Prices UK config entry: %s", entry.entry_id)
    entry_config = _entry_config(entry)
    _LOGGER.debug("Entry data: %s", _redacted_entry_data(entry_config))

    hass.data.setdefault(DOMAIN, {})
    domain_data = hass.data[DOMAIN]

    client_id = str(entry_config.get(CONF_CLIENT_ID, "")).strip()
    client_secret = str(entry_config.get(CONF_CLIENT_SECRET, "")).strip()
    if not client_id or not client_secret:
        raise ConfigEntryNotReady(
            "Fuel Finder API credentials are missing. Reconfigure the integration with a valid client ID and secret."
        )

    api_client = FuelPricesAPI(
        hass,
        client_id=client_id,
        client_secret=client_secret,
    )

    update_interval = timedelta(seconds=entry_config[CONF_UPDATE_INTERVAL])
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
    # Stagger startup refreshes across config entries to avoid hammering the API
    # with simultaneous requests when multiple locations are configured.
    domain_data.setdefault("_entry_counter", 0)
    domain_data["_entry_counter"] += 1
    stagger_delay = (domain_data["_entry_counter"] - 1) * 15  # 15s between each entry
    coordinator.start_startup_refresh(delay_seconds=stagger_delay)

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


class FuelPricesDataUpdateCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Class to manage fetching data from the Fuel Prices UK sources."""

    def __init__(self, hass, entry: ConfigEntry, update_interval: timedelta, api_client: FuelPricesAPI):
        """Initialize."""
        entry_config = _entry_config(entry)
        self.hass = hass
        self.entry = entry
        self.stations = entry_config.get(CONF_STATIONS, [])
        self.location = entry_config.get(CONF_LOCATION)
        self.radius = entry_config.get(CONF_RADIUS, 5)
        self.fuel_types = entry_config.get(CONF_FUELTYPES, ["E10", "B7"])
        self.update_interval = update_interval
        self._logger = _LOGGER
        self.api_client = api_client
        self._startup_refresh_task: asyncio.Task[None] | None = None
        self._consecutive_failures = 0
        self._first_failure_at: datetime | None = None
        self._stale_data_issue_id = f"stale_data_{entry.entry_id}"

        # Issue #10: resolve device_tracker entity_id for dynamic location
        self.device_tracker_entity_id: str | None = (
            entry_config.get(CONF_DEVICE_TRACKER)
            if entry_config.get(CONF_LOCATION_METHOD) == "device_tracker"
            else None
        )

        _LOGGER.info(
            "[coordinator][__init__] Initialising with location=%s, radius=%s km, fuel_types=%s, update_interval=%s",
            self.location,
            self.radius,
            self.fuel_types,
            update_interval,
        )

        super().__init__(
            hass,
            _LOGGER,
            name=ENTRY_TITLE,
            config_entry=entry,
            update_interval=update_interval,
            always_update=False,  # Only update if data changes to avoid unnecessary state writes
        )

    def start_startup_refresh(self, delay_seconds: int = 0) -> None:
        """Kick off one startup refresh without blocking config entry setup."""
        if self._startup_refresh_task and not self._startup_refresh_task.done():
            return

        self._startup_refresh_task = self.hass.async_create_task(
            self._async_run_startup_refresh(delay_seconds=delay_seconds),
            name=f"{DOMAIN}_{self.entry.entry_id}_startup_refresh",
        )

    def cancel_startup_refresh(self) -> None:
        """Cancel startup refresh task if it is still running."""
        if self._startup_refresh_task and not self._startup_refresh_task.done():
            self._startup_refresh_task.cancel()

    async def _async_run_startup_refresh(self, delay_seconds: int = 0) -> None:
        """Run first refresh in background so entities can appear immediately."""
        if delay_seconds > 0:
            _LOGGER.info(
                "[coordinator][startup_refresh] Staggering startup by %ds to reduce API load",
                delay_seconds,
            )
            try:
                await asyncio.sleep(delay_seconds)
            except asyncio.CancelledError:
                _LOGGER.debug("[coordinator][startup_refresh] Stagger delay cancelled")
                raise

        _LOGGER.info("[coordinator][startup_refresh] Starting background initial refresh")
        try:
            initial_success = await self._async_run_startup_refresh_attempt("initial")
            if initial_success:
                _LOGGER.info("[coordinator][startup_refresh] Initial refresh completed successfully")
                return

            _LOGGER.warning("[coordinator][startup_refresh] Initial refresh was unsuccessful; waiting 30s before retry")
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                _LOGGER.debug("[coordinator][startup_refresh] Pre-retry delay cancelled")
                raise

            retry_success = await self._async_run_startup_refresh_attempt("retry")
            if retry_success:
                _LOGGER.info("[coordinator][startup_refresh] Delayed retry completed successfully")
            else:
                _LOGGER.warning(
                    "[coordinator][startup_refresh] Delayed retry was also unsuccessful; waiting for scheduled refresh"
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

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from fuel price sources."""
        try:
            _LOGGER.info("[coordinator][_async_update_data] Starting data update cycle")

            # Determine search criteria based on configuration
            latitude = self.location.get("latitude") if self.location else None
            longitude = self.location.get("longitude") if self.location else None

            # Issue #10: override with live device_tracker coordinates if configured
            if self.device_tracker_entity_id:
                tracker_state = self.hass.states.get(self.device_tracker_entity_id)
                if tracker_state and tracker_state.state not in ("unavailable", "unknown", "not_home"):
                    try:
                        tracker_lat = tracker_state.attributes.get("latitude")
                        tracker_lon = tracker_state.attributes.get("longitude")
                        if tracker_lat is not None and tracker_lon is not None:
                            latitude = float(tracker_lat)
                            longitude = float(tracker_lon)
                            _LOGGER.debug(
                                "[coordinator][_async_update_data] Using device_tracker %s location: lat=%s, lon=%s",
                                self.device_tracker_entity_id,
                                latitude,
                                longitude,
                            )
                        else:
                            _LOGGER.warning(
                                "[coordinator][_async_update_data] device_tracker %s has no latitude/longitude attributes",
                                self.device_tracker_entity_id,
                            )
                    except (TypeError, ValueError):
                        _LOGGER.warning(
                            "[coordinator][_async_update_data] Could not parse coordinates from device_tracker %s",
                            self.device_tracker_entity_id,
                        )
                else:
                    _LOGGER.debug(
                        "[coordinator][_async_update_data] device_tracker %s state is %s; using last known location",
                        self.device_tracker_entity_id,
                        tracker_state.state if tracker_state else "<not found>",
                    )

            _LOGGER.info("[coordinator][_async_update_data] Search coordinates: lat=%s, lon=%s", latitude, longitude)
            _LOGGER.info("[coordinator][_async_update_data] Fuel types to search: %s", self.fuel_types)

            # Fetch stations based on criteria
            if latitude and longitude:
                # Radius-based search
                _LOGGER.info(
                    "[coordinator][_async_update_data] Performing radius-based search: lat=%s, lon=%s, radius=%s km",
                    latitude,
                    longitude,
                    self.radius,
                )
                stations_data = await fetch_stations_by_criteria(
                    self.api_client,
                    latitude=latitude,
                    longitude=longitude,
                    radius_km=self.radius,
                    fuel_types=self.fuel_types,
                )
            elif self.stations and len(self.stations) > 0:
                # Specific station search
                _LOGGER.debug("Performing specific station search for %s stations", len(self.stations))
                stations_data = []
                for station_config in self.stations:
                    site_id = station_config.get("site_id")
                    if site_id:
                        _LOGGER.debug("Fetching station with site_id: %s", site_id)
                        station_data = await fetch_stations_by_criteria(self.api_client, site_id=site_id)
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
            self._clear_stale_data_issue()
            return stations_data

        except asyncio.CancelledError:
            _LOGGER.debug("[coordinator][_async_update_data] Update cycle cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Error fetching data: %s", err, exc_info=True)
            self._record_failure_and_maybe_raise_repair()
            raise UpdateFailed(f"Error fetching data: {err}") from err

    def _clear_stale_data_issue(self) -> None:
        """Reset the failure streak and clear the stale-data repair on success."""
        if self._consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
            ir.async_delete_issue(self.hass, DOMAIN, self._stale_data_issue_id)
        self._consecutive_failures = 0
        self._first_failure_at = None

    def _record_failure_and_maybe_raise_repair(self) -> None:
        """Track consecutive refresh failures and surface a Repair once they pile up.

        A single failed cycle is normal (transient network blips, upstream
        API hiccups) and shouldn't alarm anyone. But once refreshes have
        failed for CONSECUTIVE_FAILURE_THRESHOLD cycles in a row, the
        displayed prices are meaningfully stale and there's currently
        nothing in the UI to say so - see GitHub issue #14, where users only
        discovered this by noticing frozen prices and digging through logs.
        """
        self._consecutive_failures += 1
        if self._first_failure_at is None:
            self._first_failure_at = datetime.now(UTC)

        if self._consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
            # Re-creating an issue with the same id updates it in place
            # (keeping failure_count/since current) rather than duplicating
            # or re-notifying, so this is safe to call on every failure once
            # the threshold is reached.
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._stale_data_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="stale_data",
                translation_placeholders={
                    "failure_count": str(self._consecutive_failures),
                    "since": self._first_failure_at.isoformat(timespec="seconds"),
                },
            )


def _redacted_entry_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return config entry data with sensitive fields masked for logging."""
    safe = dict(data)
    if CONF_CLIENT_SECRET in safe and safe[CONF_CLIENT_SECRET]:
        safe[CONF_CLIENT_SECRET] = "***REDACTED***"
    return safe
