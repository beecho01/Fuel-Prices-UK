"""Config flow for Fuel Prices UK integration."""

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlowWithConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import selector

from .api_client import async_validate_api_credentials
from .const import (
    CONF_ADDRESS,
    CONF_CHEAPEST_COUNT,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_TRACKER,
    CONF_FUELTYPES,
    CONF_LOCATION,
    CONF_LOCATION_METHOD,
    CONF_MAX_DATA_AGE_DAYS,
    CONF_NEAREST_COUNT,
    CONF_RADIUS,
    CONF_SEARCH_METHOD,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CHEAPEST_COUNT,
    DEFAULT_MAX_DATA_AGE_DAYS,
    DEFAULT_NEAREST_COUNT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENTRY_TITLE,
    FUEL_TYPES,
    KM_TO_MILES,
    MAX_CHEAPEST_COUNT,
    MAX_NEAREST_COUNT,
    MILES_TO_KM,
    MIN_CHEAPEST_COUNT,
    SCHEMA_VERSION,
)
from .location import get_lat_lon

_LOGGER = logging.getLogger(__name__)

LOCATION_METHOD_OPTIONS = {
    "map": "Drop a pin on a map",
    "address": "Enter a postcode or address",
    "device_tracker": "Use a device tracker entity",
}

# hassfest forbids raw URLs in translation strings (they can't be reviewed
# per-language and can't be updated without a full translation pass), so
# this is passed as a description_placeholders value instead of being
# embedded in strings.json/translations/en.json directly.
DOCS_URL_PLACEHOLDER = "[Fuel Finder Developer Portal](https://www.developer.fuel-finder.service.gov.uk/public-api)"


class SchemaCreationError(HomeAssistantError):
    """Error raised when the map schema cannot be produced."""


def _build_map_schema(user_input=None, hass=None):
    """Build the map configuration schema with defensive logging."""
    try:
        return main_config_schema(user_input=user_input, hass=hass)
    except Exception as exc:  # pragma: no cover - safety net for unexpected schema issues
        error_details = []
        if hasattr(exc, "errors"):
            error_details = [
                {
                    "path": list(getattr(err, "path", ())),
                    "message": getattr(err, "msg", str(err)),
                    "error": repr(err),
                }
                for err in exc.errors  # type: ignore[attr-defined]
            ]
        _LOGGER.exception(
            "[config_flow][schema] Failed to build map schema (user_input=%s, hass_available=%s, error=%r, details=%s)",
            user_input,
            hass is not None,
            exc,
            error_details,
        )
        raise SchemaCreationError("Unable to build location selector schema") from exc


def main_config_schema(user_input=None, hass=None):
    """Define the schema for the main configuration step."""
    if user_input is None:
        user_input = {}

    # Use Home Assistant's location if available
    default_location = {
        "latitude": hass.config.latitude if hass and hass.config.latitude else 51.509865,
        "longitude": hass.config.longitude if hass and hass.config.longitude else -0.118092,
    }

    # Get current radius in miles (stored value is in km, convert for display)
    radius_km = user_input.get(CONF_RADIUS, 5)  # This is in km internally
    radius_miles = round(radius_km * KM_TO_MILES, 1) if CONF_RADIUS in user_input else 3.0

    return vol.Schema(
        {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),  # 5 minutes to 24 hours
            vol.Required(CONF_RADIUS, default=radius_miles): vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=31)
            ),  # 0.5 to 31 miles (roughly 1-50 km)
            vol.Required(
                CONF_LOCATION,
                default=user_input.get(CONF_LOCATION, default_location),
            ): selector({"location": {"icon": "mdi:gas-station"}}),
            vol.Required(
                CONF_FUELTYPES,
                default=user_input.get(CONF_FUELTYPES, ["E10", "B7"]),
            ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
            vol.Required(
                CONF_CHEAPEST_COUNT,
                default=user_input.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
            vol.Required(
                CONF_NEAREST_COUNT,
                default=user_input.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
            vol.Optional(
                CONF_MAX_DATA_AGE_DAYS,
                default=user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
        }
    )


class FuelPricesUKFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Config flow for Fuel Prices UK."""

    VERSION = SCHEMA_VERSION

    def __init__(self):
        """Initialize."""
        self._errors = {}
        self._data = {}
        self._location_method = None

    async def async_step_import(self, import_data: dict) -> ConfigFlowResult:
        """Handle import from configuration.yaml.

        Credentials are read from the YAML block (supporting !secret) and a
        config entry is created without requiring any UI interaction.  If an
        entry with the same client_id already exists the import is silently
        aborted so duplicate entries are not created on every HA restart.
        """
        _LOGGER.debug("[config_flow][step_import] YAML import triggered")

        client_id = str(import_data.get(CONF_CLIENT_ID, "")).strip()
        client_secret = str(import_data.get(CONF_CLIENT_SECRET, "")).strip()
        name = str(import_data.get("name", "")).strip()

        if not client_id or not client_secret:
            _LOGGER.error("[config_flow][step_import] Missing client_id or client_secret in YAML config")
            return self.async_abort(reason="missing_credentials")

        # Unique ID: combine client_id with name so two locations that share
        # the same API credentials can coexist as separate config entries.
        unique_id = f"{client_id}:{name}" if name else client_id
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        credentials_valid = await async_validate_api_credentials(self.hass, client_id, client_secret)
        if not credentials_valid:
            _LOGGER.error(
                "[config_flow][step_import] YAML credentials failed validation — check client_id/client_secret"
            )
            return self.async_abort(reason="invalid_api_credentials")

        # --- Location ---
        # Priority: postcode → address → lat+long → HA home
        address_block = import_data.get("location") or {}
        postcode = str(address_block.get("postcode", "")).strip()
        freetext = str(address_block.get("address", "")).strip()
        lat = address_block.get("lat")
        lon = address_block.get("long")

        if postcode:
            lookup_text = postcode
            resolved_lat, resolved_lon = await self.hass.async_add_executor_job(get_lat_lon, lookup_text)
            if resolved_lat is None or resolved_lon is None:
                _LOGGER.error(
                    "[config_flow][step_import] Could not resolve postcode from YAML: %s",
                    postcode,
                )
                return self.async_abort(reason="invalid_address")
            location_method = "address"
            location = {"latitude": resolved_lat, "longitude": resolved_lon}
            address = postcode
        elif freetext:
            resolved_lat, resolved_lon = await self.hass.async_add_executor_job(get_lat_lon, freetext)
            if resolved_lat is None or resolved_lon is None:
                _LOGGER.error(
                    "[config_flow][step_import] Could not geocode address from YAML: %s",
                    freetext,
                )
                return self.async_abort(reason="invalid_address")
            location_method = "address"
            location = {"latitude": resolved_lat, "longitude": resolved_lon}
            address = freetext
        elif lat is not None and lon is not None:
            location_method = "map"
            location = {"latitude": float(lat), "longitude": float(lon)}
            address = ""
        else:
            # Fall back to HA's configured home location.
            location_method = "map"
            location = {
                "latitude": self.hass.config.latitude,
                "longitude": self.hass.config.longitude,
            }
            address = ""
            _LOGGER.info(
                "[config_flow][step_import] No address in YAML; using HA home (%s, %s)",
                location["latitude"],
                location["longitude"],
            )

        # --- Radius ---
        radius_block = import_data.get("radius") or {}
        radius_value = float(radius_block.get("value", 3.0))
        radius_type = str(radius_block.get("type", "miles")).lower()
        if radius_type == "km":
            radius_km = round(radius_value, 1)
            radius_display = round(radius_value * KM_TO_MILES, 1)
        else:
            radius_km = round(radius_value * MILES_TO_KM, 1)
            radius_display = round(radius_value, 1)

        # --- Fuel types ---
        fuel_types_block = import_data.get("fuel_types") or {}
        fuel_types = [ft for ft, enabled in fuel_types_block.items() if enabled] if fuel_types_block else ["E10", "B7"]

        # --- Sensor counts ---
        count_block = import_data.get("count") or {}
        cheapest_count = int(count_block.get("cheapest", DEFAULT_CHEAPEST_COUNT))
        nearest_count = int(count_block.get("nearest", DEFAULT_NEAREST_COUNT))

        if cheapest_count == 0 and nearest_count == 0:
            _LOGGER.warning(
                "[config_flow][step_import] Both count.cheapest and count.nearest are 0 in YAML config; "
                "no sensors will be created. Set at least one to a value > 0."
            )

        # --- Stale data filter ---
        max_data_age_days = int(import_data.get("ignore_stale_data_days", DEFAULT_MAX_DATA_AGE_DAYS))
        update_interval = int(import_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))

        if name:
            title = name
        elif address:
            title = f"{ENTRY_TITLE} - {address[:20]} - {radius_display}mi"
        elif lat is not None and lon is not None:
            title = f"{ENTRY_TITLE} - {float(lat):.4f}, {float(lon):.4f} - {radius_display}mi"
        else:
            title = f"{ENTRY_TITLE} ({radius_display} mi)"

        return self.async_create_entry(
            title=title,
            data={
                CONF_CLIENT_ID: client_id,
                CONF_CLIENT_SECRET: client_secret,
                CONF_LOCATION_METHOD: location_method,
                CONF_LOCATION: location,
                CONF_ADDRESS: address,
                CONF_RADIUS: radius_km,
                CONF_FUELTYPES: fuel_types,
                CONF_CHEAPEST_COUNT: cheapest_count,
                CONF_NEAREST_COUNT: nearest_count,
                CONF_UPDATE_INTERVAL: update_interval,
                CONF_MAX_DATA_AGE_DAYS: max_data_age_days,
                CONF_STATIONS: [],
            },
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step - credentials and location input method."""
        _LOGGER.debug("[config_flow][step_user] Started - choosing location method")
        self._errors = {}

        if user_input is not None:
            client_id = str(user_input.get(CONF_CLIENT_ID, "")).strip()
            client_secret = str(user_input.get(CONF_CLIENT_SECRET, "")).strip()

            if not client_id or not client_secret:
                self._errors["base"] = "invalid_api_credentials"
            else:
                credentials_valid = await async_validate_api_credentials(
                    self.hass,
                    client_id,
                    client_secret,
                )
                if not credentials_valid:
                    self._errors["base"] = "invalid_api_credentials"

            if self._errors:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_SEARCH_METHOD,
                                default=user_input.get(CONF_SEARCH_METHOD, "map"),
                            ): vol.In(LOCATION_METHOD_OPTIONS),
                            vol.Required(
                                CONF_CLIENT_ID,
                                default=user_input.get(CONF_CLIENT_ID, ""),
                            ): cv.string,
                            vol.Required(CONF_CLIENT_SECRET): selector({"text": {"type": "password"}}),
                        }
                    ),
                    errors=self._errors,
                    description_placeholders={
                        "info": "Choose how you want to specify your location and provide your Fuel Finder API credentials.",
                        "docs_url": DOCS_URL_PLACEHOLDER,
                    },
                )

            self._data[CONF_CLIENT_ID] = client_id
            self._data[CONF_CLIENT_SECRET] = client_secret
            self._location_method = user_input[CONF_SEARCH_METHOD]
            _LOGGER.debug("[config_flow][step_user] Selected method: %s", self._location_method)

            if self._location_method == "map":
                return await self.async_step_location_map()
            elif self._location_method == "device_tracker":
                return await self.async_step_location_device_tracker()
            else:
                return await self.async_step_location_address()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SEARCH_METHOD, default="map"): vol.In(LOCATION_METHOD_OPTIONS),
                    vol.Required(CONF_CLIENT_ID): cv.string,
                    vol.Required(CONF_CLIENT_SECRET): selector({"text": {"type": "password"}}),
                }
            ),
            description_placeholders={
                "info": "Choose how you want to specify your location and provide your Fuel Finder API credentials.",
                "docs_url": DOCS_URL_PLACEHOLDER,
            },
        )

    async def async_step_location_map(self, user_input=None):
        """Handle map-based location input."""
        _LOGGER.debug("[config_flow][step_location_map] Started")
        self._errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="location_map",
                data_schema=_build_map_schema(hass=self.hass),
                description_placeholders={
                    "info": "Configure your fuel price monitoring. Stations within the specified radius of your location will be monitored."
                },
            )

        try:
            # Validate inputs
            if user_input[CONF_UPDATE_INTERVAL] < 300:
                raise InvalidUpdateInterval("Update interval must be at least 5 minutes")

            if user_input[CONF_RADIUS] <= 0:
                raise InvalidRadius("Radius must be greater than 0")

            if not user_input.get(CONF_FUELTYPES):
                raise NoFuelTypeSelected("At least one fuel type must be selected")

            cheapest_count = int(user_input.get(CONF_CHEAPEST_COUNT) or 0)
            nearest_count = int(user_input.get(CONF_NEAREST_COUNT) or 0)
            if cheapest_count == 0 and nearest_count == 0:
                raise NeitherOptionEnabled("Enable at least one of cheapest or nearest stations")

            # Convert radius from miles to km for storage
            radius_miles = user_input[CONF_RADIUS]
            radius_km = round(radius_miles * MILES_TO_KM, 1)

            location_raw = user_input.get(CONF_LOCATION)
            _LOGGER.debug(
                "[config_flow][step_location_map] Raw location selector payload: %s",
                location_raw,
            )

            latitude, longitude = _extract_coordinates(location_raw)
            _LOGGER.debug(
                "[config_flow][step_location_map] Normalised coordinates -> lat=%s, lon=%s",
                latitude,
                longitude,
            )
            if latitude is None or longitude is None:
                raise InvalidLocation("Map selection must include latitude and longitude")

            # Store the configuration (radius stored in km for API)
            self._data = {
                CONF_CLIENT_ID: self._data.get(CONF_CLIENT_ID),
                CONF_CLIENT_SECRET: self._data.get(CONF_CLIENT_SECRET),
                CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                CONF_LOCATION: {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                CONF_LOCATION_METHOD: "map",
                CONF_RADIUS: radius_km,  # Store in km
                CONF_FUELTYPES: user_input[CONF_FUELTYPES],
                CONF_CHEAPEST_COUNT: cheapest_count,
                CONF_NEAREST_COUNT: nearest_count,
                CONF_MAX_DATA_AGE_DAYS: user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                CONF_STATIONS: [],  # Will be populated with actual stations during runtime
            }

            # Create a descriptive title (show in miles)
            title = f"{ENTRY_TITLE} - {radius_miles}mi radius"

            return self.async_create_entry(title=title, data=self._data)

        except InvalidUpdateInterval:
            self._errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
        except InvalidRadius:
            self._errors[CONF_RADIUS] = "invalid_radius"
        except NoFuelTypeSelected:
            self._errors[CONF_FUELTYPES] = "no_fuel_type_selected"
        except NeitherOptionEnabled:
            self._errors["base"] = "neither_option_enabled"
        except InvalidLocation:
            self._errors[CONF_LOCATION] = "invalid_location"
        except Exception as e:
            _LOGGER.exception(
                "[config_flow][step_location_map] Unexpected exception (raw=%r, user_input=%s)",
                e,
                user_input,
            )
            self._errors["base"] = "unknown"

        return self.async_show_form(
            step_id="location_map",
            data_schema=_build_map_schema(user_input, hass=self.hass),
            errors=self._errors,
        )

    async def async_step_location_address(self, user_input=None):
        """Handle address/postcode-based location input."""
        _LOGGER.debug("[config_flow][step_location_address] Started")
        self._errors = {}

        if user_input is None:
            # Get default radius (3 miles)
            default_radius = 3.0

            return self.async_show_form(
                step_id="location_address",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_UPDATE_INTERVAL,
                            default=DEFAULT_UPDATE_INTERVAL,
                        ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                        vol.Required(CONF_RADIUS, default=default_radius): vol.All(
                            vol.Coerce(float), vol.Range(min=0.5, max=31)
                        ),
                        vol.Required(CONF_ADDRESS): cv.string,
                        vol.Required(
                            CONF_FUELTYPES,
                            default=["E10", "B7"],
                        ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                        vol.Required(
                            CONF_CHEAPEST_COUNT,
                            default=DEFAULT_CHEAPEST_COUNT,
                        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
                        vol.Optional(
                            CONF_NEAREST_COUNT,
                            default=DEFAULT_NEAREST_COUNT,
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
                        vol.Optional(
                            CONF_MAX_DATA_AGE_DAYS,
                            default=DEFAULT_MAX_DATA_AGE_DAYS,
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                    }
                ),
                description_placeholders={
                    "info": "Enter a UK postcode, address, or location name. We'll find the coordinates for you."
                },
            )

        try:
            # Validate inputs
            if user_input[CONF_UPDATE_INTERVAL] < 300:
                raise InvalidUpdateInterval("Update interval must be at least 5 minutes")

            if user_input[CONF_RADIUS] <= 0:
                raise InvalidRadius("Radius must be greater than 0")

            if not user_input.get(CONF_FUELTYPES):
                raise NoFuelTypeSelected("At least one fuel type must be selected")

            cheapest_count = int(user_input.get(CONF_CHEAPEST_COUNT) or 0)
            nearest_count = int(user_input.get(CONF_NEAREST_COUNT) or 0)
            if cheapest_count == 0 and nearest_count == 0:
                raise NeitherOptionEnabled("Enable at least one of cheapest or nearest stations")

            # Convert address/postcode to coordinates
            address = user_input[CONF_ADDRESS]
            _LOGGER.debug("[config_flow][step_location_address] Looking up: %s", address)

            lat, lon = await self.hass.async_add_executor_job(get_lat_lon, address)

            if lat is None or lon is None:
                _LOGGER.warning("[config_flow][step_location_address] Could not find location for: %s", address)
                raise InvalidAddress("Could not find location. Please check your postcode/address and try again.")

            _LOGGER.info("[config_flow][step_location_address] Found coordinates: %s, %s for '%s'", lat, lon, address)

            # Convert radius from miles to km for storage
            radius_miles = user_input[CONF_RADIUS]
            radius_km = round(radius_miles * MILES_TO_KM, 1)

            # Store the configuration (radius stored in km for API)
            self._data = {
                CONF_CLIENT_ID: self._data.get(CONF_CLIENT_ID),
                CONF_CLIENT_SECRET: self._data.get(CONF_CLIENT_SECRET),
                CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                CONF_LOCATION: {
                    "latitude": lat,
                    "longitude": lon,
                },
                CONF_LOCATION_METHOD: "address",
                CONF_ADDRESS: address,  # Store original address for reference
                CONF_RADIUS: radius_km,  # Store in km
                CONF_FUELTYPES: user_input[CONF_FUELTYPES],
                CONF_CHEAPEST_COUNT: cheapest_count,
                CONF_NEAREST_COUNT: nearest_count,
                CONF_MAX_DATA_AGE_DAYS: user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                CONF_STATIONS: [],  # Will be populated with actual stations during runtime
            }

            # Create a descriptive title (show in miles and address)
            title = f"{ENTRY_TITLE} - {address[:20]} - {radius_miles}mi"

            return self.async_create_entry(title=title, data=self._data)

        except InvalidUpdateInterval:
            self._errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
        except InvalidRadius:
            self._errors[CONF_RADIUS] = "invalid_radius"
        except NoFuelTypeSelected:
            self._errors[CONF_FUELTYPES] = "no_fuel_type_selected"
        except NeitherOptionEnabled:
            self._errors["base"] = "neither_option_enabled"
        except InvalidAddress:
            self._errors[CONF_ADDRESS] = "invalid_address"
        except Exception as e:
            _LOGGER.exception("Unexpected error during address lookup: %s", e)
            self._errors["base"] = "unknown"

        return self.async_show_form(
            step_id="location_address",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Required(CONF_RADIUS, default=user_input.get(CONF_RADIUS, 3.0)): vol.All(
                        vol.Coerce(float), vol.Range(min=0.5, max=31)
                    ),
                    vol.Required(CONF_ADDRESS, default=user_input.get(CONF_ADDRESS, "")): cv.string,
                    vol.Required(
                        CONF_FUELTYPES,
                        default=user_input.get(CONF_FUELTYPES, ["E10", "B7"]),
                    ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                    vol.Required(
                        CONF_CHEAPEST_COUNT,
                        default=user_input.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
                    vol.Required(
                        CONF_NEAREST_COUNT,
                        default=user_input.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
                    vol.Optional(
                        CONF_MAX_DATA_AGE_DAYS,
                        default=user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                }
            ),
            errors=self._errors,
        )

    async def async_step_location_device_tracker(self, user_input=None):
        """Handle device tracker-based location input."""
        _LOGGER.debug("[config_flow][step_location_device_tracker] Started")
        self._errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="location_device_tracker",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_DEVICE_TRACKER,
                        ): selector({"entity": {"domain": "device_tracker"}}),
                        vol.Required(
                            CONF_UPDATE_INTERVAL,
                            default=DEFAULT_UPDATE_INTERVAL,
                        ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                        vol.Required(
                            CONF_RADIUS,
                            default=3.0,
                        ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),
                        vol.Required(
                            CONF_FUELTYPES,
                            default=["E10", "B7"],
                        ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                        vol.Required(
                            CONF_CHEAPEST_COUNT,
                            default=DEFAULT_CHEAPEST_COUNT,
                        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
                        vol.Required(
                            CONF_NEAREST_COUNT,
                            default=DEFAULT_NEAREST_COUNT,
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
                        vol.Optional(
                            CONF_MAX_DATA_AGE_DAYS,
                            default=DEFAULT_MAX_DATA_AGE_DAYS,
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                    }
                ),
            )

        tracker_entity_id = user_input.get(CONF_DEVICE_TRACKER, "")
        tracker_state = self.hass.states.get(tracker_entity_id) if tracker_entity_id else None
        cheapest_count = int(user_input.get(CONF_CHEAPEST_COUNT) or 0)
        nearest_count = int(user_input.get(CONF_NEAREST_COUNT) or 0)

        if not tracker_state:
            self._errors[CONF_DEVICE_TRACKER] = "device_tracker_not_found"
        elif tracker_state.attributes.get("latitude") is None:
            self._errors[CONF_DEVICE_TRACKER] = "device_tracker_no_location"
        elif cheapest_count == 0 and nearest_count == 0:
            self._errors["base"] = "neither_option_enabled"

        if self._errors:
            return self.async_show_form(
                step_id="location_device_tracker",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_DEVICE_TRACKER, default=tracker_entity_id): selector(
                            {"entity": {"domain": "device_tracker"}}
                        ),
                        vol.Required(
                            CONF_UPDATE_INTERVAL, default=user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                        ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                        vol.Required(CONF_RADIUS, default=user_input.get(CONF_RADIUS, 3.0)): vol.All(
                            vol.Coerce(float), vol.Range(min=0.5, max=31)
                        ),
                        vol.Required(
                            CONF_FUELTYPES, default=user_input.get(CONF_FUELTYPES, ["E10", "B7"])
                        ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                        vol.Required(
                            CONF_CHEAPEST_COUNT, default=user_input.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT)
                        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
                        vol.Required(
                            CONF_NEAREST_COUNT, default=user_input.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT)
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
                        vol.Optional(
                            CONF_MAX_DATA_AGE_DAYS,
                            default=user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                    }
                ),
                errors=self._errors,
            )

        radius_miles = user_input[CONF_RADIUS]
        radius_km = round(radius_miles * MILES_TO_KM, 1)

        self._data = {
            CONF_CLIENT_ID: self._data.get(CONF_CLIENT_ID),
            CONF_CLIENT_SECRET: self._data.get(CONF_CLIENT_SECRET),
            CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
            CONF_LOCATION_METHOD: "device_tracker",
            CONF_DEVICE_TRACKER: tracker_entity_id,
            CONF_LOCATION: {},
            CONF_RADIUS: radius_km,
            CONF_FUELTYPES: user_input[CONF_FUELTYPES],
            CONF_CHEAPEST_COUNT: cheapest_count,
            CONF_NEAREST_COUNT: nearest_count,
            CONF_MAX_DATA_AGE_DAYS: user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
            CONF_STATIONS: [],
        }

        title = f"{ENTRY_TITLE} - {tracker_entity_id} - {radius_miles}mi"
        return self.async_create_entry(title=title, data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "OptionsFlowHandler":
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlowWithConfigEntry):
    """Handle options flow for Fuel Prices UK."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        self._errors = {}
        self._resolved_client_id = str(config_entry.data.get(CONF_CLIENT_ID, "")).strip()
        self._resolved_client_secret = str(config_entry.data.get(CONF_CLIENT_SECRET, "")).strip()

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Manage the options - choose location method and optional credential updates."""
        # Get current location method (default to map if not set for backwards compatibility)
        merged_init = dict(self.config_entry.data)
        merged_init.update(self.config_entry.options)
        current_method = merged_init.get(CONF_LOCATION_METHOD, "map")

        if user_input is not None:
            self._errors = {}

            proposed_client_id = str(user_input.get(CONF_CLIENT_ID, "")).strip()
            proposed_client_secret = str(user_input.get(CONF_CLIENT_SECRET, "")).strip()

            if proposed_client_id:
                self._resolved_client_id = proposed_client_id
            if proposed_client_secret:
                self._resolved_client_secret = proposed_client_secret

            if not self._resolved_client_id or not self._resolved_client_secret:
                self._errors["base"] = "invalid_api_credentials"
            else:
                credentials_changed = self._resolved_client_id != str(
                    self.config_entry.data.get(CONF_CLIENT_ID, "")
                ).strip() or bool(proposed_client_secret)
                if credentials_changed:
                    credentials_valid = await async_validate_api_credentials(
                        self.hass,
                        self._resolved_client_id,
                        self._resolved_client_secret,
                    )
                    if not credentials_valid:
                        self._errors["base"] = "invalid_api_credentials"

            if self._errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_SEARCH_METHOD,
                                default=user_input.get(CONF_SEARCH_METHOD, current_method),
                            ): vol.In(LOCATION_METHOD_OPTIONS),
                            vol.Required(
                                CONF_CLIENT_ID,
                                default=user_input.get(CONF_CLIENT_ID, self._resolved_client_id),
                            ): cv.string,
                            vol.Optional(CONF_CLIENT_SECRET, default=""): selector({"text": {"type": "password"}}),
                        }
                    ),
                    errors=self._errors,
                    description_placeholders={
                        "info": "Choose how you want to update your location and optionally rotate your Fuel Finder API credentials.",
                        "docs_url": DOCS_URL_PLACEHOLDER,
                    },
                )

            if user_input[CONF_SEARCH_METHOD] == "map":
                return await self.async_step_location_map()
            elif user_input[CONF_SEARCH_METHOD] == "device_tracker":
                return await self.async_step_location_device_tracker()
            else:
                return await self.async_step_location_address()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SEARCH_METHOD, default=current_method): vol.In(LOCATION_METHOD_OPTIONS),
                    vol.Required(
                        CONF_CLIENT_ID,
                        default=self._resolved_client_id,
                    ): cv.string,
                    vol.Optional(CONF_CLIENT_SECRET, default=""): selector({"text": {"type": "password"}}),
                }
            ),
            description_placeholders={
                "info": "Choose how you want to update your location and optionally rotate your Fuel Finder API credentials.",
                "docs_url": DOCS_URL_PLACEHOLDER,
            },
            errors=self._errors,
        )

    async def async_step_location_map(self, user_input=None) -> ConfigFlowResult:
        """Handle map-based location options."""
        self._errors = {}
        if user_input is not None:
            # Convert radius from miles to km before saving
            radius_miles = user_input[CONF_RADIUS]
            radius_km = round(radius_miles * MILES_TO_KM, 1)

            location_raw = user_input.get(CONF_LOCATION)
            _LOGGER.debug(
                "[options_flow][step_location_map] Raw location selector payload: %s",
                location_raw,
            )
            latitude, longitude = _extract_coordinates(location_raw)
            if latitude is None or longitude is None:
                self._errors = {CONF_LOCATION: "invalid_location"}
            else:
                # Preserve existing data and update with new values
                updated_data = dict(self.config_entry.data)
                updated_data[CONF_CLIENT_ID] = self._resolved_client_id
                updated_data[CONF_CLIENT_SECRET] = self._resolved_client_secret
                updated_data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
                updated_data[CONF_LOCATION] = {
                    "latitude": latitude,
                    "longitude": longitude,
                }
                updated_data[CONF_LOCATION_METHOD] = "map"
                updated_data[CONF_RADIUS] = radius_km
                cheapest_count = int(user_input.get(CONF_CHEAPEST_COUNT) or 0)
                nearest_count = int(user_input.get(CONF_NEAREST_COUNT) or 0)
                if cheapest_count == 0 and nearest_count == 0:
                    self._errors["base"] = "neither_option_enabled"
                    return self.async_show_form(
                        step_id="location_map",
                        data_schema=vol.Schema(
                            {
                                vol.Required(
                                    CONF_UPDATE_INTERVAL,
                                    default=user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                                ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                                vol.Required(CONF_RADIUS, default=user_input.get(CONF_RADIUS, 3.0)): vol.All(
                                    vol.Coerce(float), vol.Range(min=0.5, max=31)
                                ),
                                vol.Required(CONF_LOCATION, default=user_input.get(CONF_LOCATION)): selector(
                                    {"location": {"icon": "mdi:gas-station"}}
                                ),
                                vol.Required(
                                    CONF_FUELTYPES, default=user_input.get(CONF_FUELTYPES, ["E10", "B7"])
                                ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                                vol.Required(CONF_CHEAPEST_COUNT, default=cheapest_count): vol.All(
                                    vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)
                                ),
                                vol.Required(CONF_NEAREST_COUNT, default=nearest_count): vol.All(
                                    vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)
                                ),
                                vol.Optional(
                                    CONF_MAX_DATA_AGE_DAYS,
                                    default=user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                            }
                        ),
                        errors=self._errors,
                    )
                updated_data[CONF_FUELTYPES] = user_input[CONF_FUELTYPES]
                updated_data[CONF_CHEAPEST_COUNT] = cheapest_count
                updated_data[CONF_NEAREST_COUNT] = nearest_count
                updated_data[CONF_MAX_DATA_AGE_DAYS] = user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS)

                # Remove address if it was set before
                if CONF_ADDRESS in updated_data:
                    del updated_data[CONF_ADDRESS]

                return self.async_create_entry(title="", data=updated_data)

        # Get current radius in miles (stored in km, convert for display)
        # Use merged config so options-flow values are shown, not stale entry.data
        merged = dict(self.config_entry.data)
        merged.update(self.config_entry.options)
        radius_km = merged.get(CONF_RADIUS, 5)
        radius_miles = round(radius_km * KM_TO_MILES, 1)

        return self.async_show_form(
            step_id="location_map",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Required(
                        CONF_RADIUS,
                        default=radius_miles,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),  # 0.5 to 31 miles
                    vol.Required(
                        CONF_LOCATION,
                        default=merged.get(CONF_LOCATION),
                    ): selector({"location": {"icon": "mdi:gas-station"}}),
                    vol.Required(
                        CONF_FUELTYPES,
                        default=merged.get(CONF_FUELTYPES, ["E10", "B7"]),
                    ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                    vol.Required(
                        CONF_CHEAPEST_COUNT,
                        default=merged.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
                    vol.Required(
                        CONF_NEAREST_COUNT,
                        default=merged.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
                    vol.Optional(
                        CONF_MAX_DATA_AGE_DAYS,
                        default=merged.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                }
            ),
            errors=self._errors,
        )

    async def async_step_location_address(self, user_input=None) -> ConfigFlowResult:
        """Handle address/postcode-based location options."""
        self._errors = {}

        if user_input is not None:
            try:
                # Validate inputs
                if user_input[CONF_UPDATE_INTERVAL] < 300:
                    raise InvalidUpdateInterval("Update interval must be at least 5 minutes")

                if user_input[CONF_RADIUS] <= 0:
                    raise InvalidRadius("Radius must be greater than 0")

                if not user_input.get(CONF_FUELTYPES):
                    raise NoFuelTypeSelected("At least one fuel type must be selected")

                cheapest_count = int(user_input.get(CONF_CHEAPEST_COUNT) or 0)
                nearest_count = int(user_input.get(CONF_NEAREST_COUNT) or 0)
                if cheapest_count == 0 and nearest_count == 0:
                    raise NeitherOptionEnabled("Enable at least one of cheapest or nearest stations")

                # Convert address/postcode to coordinates
                address = user_input[CONF_ADDRESS]
                _LOGGER.debug("[options_flow][step_location_address] Looking up: %s", address)

                lat, lon = await self.hass.async_add_executor_job(get_lat_lon, address)

                if lat is None or lon is None:
                    _LOGGER.warning("[options_flow][step_location_address] Could not find location for: %s", address)
                    raise InvalidAddress("Could not find location. Please check your postcode/address and try again.")

                _LOGGER.info(
                    "[options_flow][step_location_address] Found coordinates: %s, %s for '%s'", lat, lon, address
                )

                # Convert radius from miles to km for storage
                radius_miles = user_input[CONF_RADIUS]
                radius_km = round(radius_miles * MILES_TO_KM, 1)

                # Preserve existing data and update with new values
                updated_data = dict(self.config_entry.data)
                updated_data[CONF_CLIENT_ID] = self._resolved_client_id
                updated_data[CONF_CLIENT_SECRET] = self._resolved_client_secret
                updated_data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
                updated_data[CONF_LOCATION] = {
                    "latitude": lat,
                    "longitude": lon,
                }
                updated_data[CONF_LOCATION_METHOD] = "address"
                updated_data[CONF_ADDRESS] = address
                updated_data[CONF_RADIUS] = radius_km
                updated_data[CONF_FUELTYPES] = user_input[CONF_FUELTYPES]
                updated_data[CONF_CHEAPEST_COUNT] = cheapest_count
                updated_data[CONF_NEAREST_COUNT] = nearest_count
                updated_data[CONF_MAX_DATA_AGE_DAYS] = user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS)

                return self.async_create_entry(title="", data=updated_data)

            except InvalidUpdateInterval:
                self._errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
            except InvalidRadius:
                self._errors[CONF_RADIUS] = "invalid_radius"
            except NoFuelTypeSelected:
                self._errors[CONF_FUELTYPES] = "no_fuel_type_selected"
            except NeitherOptionEnabled:
                self._errors["base"] = "neither_option_enabled"
            except InvalidAddress:
                self._errors[CONF_ADDRESS] = "invalid_address"
            except Exception as e:
                _LOGGER.exception(
                    "[options_flow][step_location_address] Unexpected exception (raw=%r, user_input=%s)",
                    e,
                    user_input,
                )
                self._errors["base"] = "unknown"

        # Get current values using merged config
        merged = dict(self.config_entry.data)
        merged.update(self.config_entry.options)
        radius_km = merged.get(CONF_RADIUS, 5)
        radius_miles = round(radius_km * KM_TO_MILES, 1)
        current_address = merged.get(CONF_ADDRESS, "")

        return self.async_show_form(
            step_id="location_address",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=user_input.get(
                            CONF_UPDATE_INTERVAL, merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                        )
                        if user_input
                        else merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Required(
                        CONF_RADIUS, default=user_input.get(CONF_RADIUS, radius_miles) if user_input else radius_miles
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),
                    vol.Required(
                        CONF_ADDRESS,
                        default=user_input.get(CONF_ADDRESS, current_address) if user_input else current_address,
                    ): cv.string,
                    vol.Required(
                        CONF_FUELTYPES,
                        default=user_input.get(CONF_FUELTYPES, merged.get(CONF_FUELTYPES, ["E10", "B7"]))
                        if user_input
                        else merged.get(CONF_FUELTYPES, ["E10", "B7"]),
                    ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                    vol.Required(
                        CONF_CHEAPEST_COUNT,
                        default=user_input.get(
                            CONF_CHEAPEST_COUNT, merged.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT)
                        )
                        if user_input
                        else merged.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
                    vol.Required(
                        CONF_NEAREST_COUNT,
                        default=user_input.get(
                            CONF_NEAREST_COUNT, merged.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT)
                        )
                        if user_input
                        else merged.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
                    vol.Optional(
                        CONF_MAX_DATA_AGE_DAYS,
                        default=user_input.get(
                            CONF_MAX_DATA_AGE_DAYS, merged.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS)
                        )
                        if user_input
                        else merged.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                }
            ),
            errors=self._errors,
        )

    async def async_step_location_device_tracker(self, user_input=None) -> ConfigFlowResult:
        """Handle device tracker-based location options."""
        _LOGGER.debug("[options_flow][step_location_device_tracker] Started")
        self._errors = {}
        merged = dict(self.config_entry.data)
        merged.update(self.config_entry.options)

        if user_input is not None:
            tracker_entity_id = user_input.get(CONF_DEVICE_TRACKER, "")
            tracker_state = self.hass.states.get(tracker_entity_id) if tracker_entity_id else None
            if not tracker_state:
                self._errors[CONF_DEVICE_TRACKER] = "device_tracker_not_found"
            elif tracker_state.attributes.get("latitude") is None:
                self._errors[CONF_DEVICE_TRACKER] = "device_tracker_no_location"

            cheapest_count = int(user_input.get(CONF_CHEAPEST_COUNT) or 0)
            nearest_count = int(user_input.get(CONF_NEAREST_COUNT) or 0)
            if not self._errors and cheapest_count == 0 and nearest_count == 0:
                self._errors["base"] = "neither_option_enabled"

            if not self._errors:
                radius_miles = user_input[CONF_RADIUS]
                radius_km = round(radius_miles * MILES_TO_KM, 1)
                updated_data = dict(self.config_entry.data)
                updated_data[CONF_CLIENT_ID] = self._resolved_client_id
                updated_data[CONF_CLIENT_SECRET] = self._resolved_client_secret
                updated_data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
                updated_data[CONF_LOCATION_METHOD] = "device_tracker"
                updated_data[CONF_DEVICE_TRACKER] = tracker_entity_id
                updated_data[CONF_LOCATION] = {}
                updated_data[CONF_RADIUS] = radius_km
                updated_data[CONF_FUELTYPES] = user_input[CONF_FUELTYPES]
                updated_data[CONF_CHEAPEST_COUNT] = cheapest_count
                updated_data[CONF_NEAREST_COUNT] = nearest_count
                updated_data[CONF_MAX_DATA_AGE_DAYS] = user_input.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS)
                if CONF_ADDRESS in updated_data:
                    del updated_data[CONF_ADDRESS]
                return self.async_create_entry(title="", data=updated_data)

        current_tracker = merged.get(CONF_DEVICE_TRACKER, "")
        current_radius_km = merged.get(CONF_RADIUS, 5)
        current_radius_miles = round(current_radius_km * KM_TO_MILES, 1)

        return self.async_show_form(
            step_id="location_device_tracker",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_TRACKER,
                        default=user_input.get(CONF_DEVICE_TRACKER, current_tracker) if user_input else current_tracker,
                    ): selector({"entity": {"domain": "device_tracker"}}),
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=user_input.get(
                            CONF_UPDATE_INTERVAL, merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                        )
                        if user_input
                        else merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Required(
                        CONF_RADIUS,
                        default=user_input.get(CONF_RADIUS, current_radius_miles)
                        if user_input
                        else current_radius_miles,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),
                    vol.Required(
                        CONF_FUELTYPES,
                        default=user_input.get(CONF_FUELTYPES, merged.get(CONF_FUELTYPES, ["E10", "B7"]))
                        if user_input
                        else merged.get(CONF_FUELTYPES, ["E10", "B7"]),
                    ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                    vol.Required(
                        CONF_CHEAPEST_COUNT,
                        default=user_input.get(
                            CONF_CHEAPEST_COUNT, merged.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT)
                        )
                        if user_input
                        else merged.get(CONF_CHEAPEST_COUNT, DEFAULT_CHEAPEST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_CHEAPEST_COUNT, max=MAX_CHEAPEST_COUNT)),
                    vol.Required(
                        CONF_NEAREST_COUNT,
                        default=user_input.get(
                            CONF_NEAREST_COUNT, merged.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT)
                        )
                        if user_input
                        else merged.get(CONF_NEAREST_COUNT, DEFAULT_NEAREST_COUNT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_NEAREST_COUNT)),
                    vol.Optional(
                        CONF_MAX_DATA_AGE_DAYS,
                        default=user_input.get(
                            CONF_MAX_DATA_AGE_DAYS, merged.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS)
                        )
                        if user_input
                        else merged.get(CONF_MAX_DATA_AGE_DAYS, DEFAULT_MAX_DATA_AGE_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                }
            ),
            errors=self._errors,
        )


class InvalidRadius(HomeAssistantError):
    """Error to indicate an invalid radius."""


class InvalidUpdateInterval(HomeAssistantError):
    """Error to indicate the update interval is invalid."""


class NoFuelTypeSelected(HomeAssistantError):
    """Error to indicate no fuel type was selected."""


class NeitherOptionEnabled(HomeAssistantError):
    """Error when neither cheapest nor nearest sensors are enabled."""


class InvalidCheapestCount(HomeAssistantError):
    """Error to indicate the cheapest options count is invalid."""


class InvalidAddress(HomeAssistantError):
    """Error to indicate an invalid address or postcode."""


class InvalidLocation(HomeAssistantError):
    """Error to indicate an invalid map selection."""


def _extract_coordinates(location_input):
    if not isinstance(location_input, dict):
        return None, None
    latitude = location_input.get("latitude")
    longitude = location_input.get("longitude")
    if latitude is None or longitude is None:
        return None, None
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None, None
    return lat, lon
