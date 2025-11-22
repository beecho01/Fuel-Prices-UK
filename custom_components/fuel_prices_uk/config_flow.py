"""Config flow for Fuel Prices UK integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlowWithConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SCHEMA_VERSION,
    CONF_UPDATE_INTERVAL,
    CONF_STATIONS,
    CONF_FUELTYPES,
    CONF_LOCATION,
    CONF_LOCATION_METHOD,
    CONF_ADDRESS,
    CONF_RADIUS,
    CONF_SEARCH_METHOD,
    CONF_SITE_ID,
    ENTRY_TITLE,
    NAME,
    FUEL_TYPES,
    DEFAULT_UPDATE_INTERVAL,
    MILES_TO_KM,
    KM_TO_MILES,
)
from .location import get_lat_lon

_LOGGER = logging.getLogger(__name__)


class SchemaCreationError(HomeAssistantError):
    """Error raised when the map schema cannot be produced."""



def _build_map_schema(user_input=None, hass=None):
    """Build the map configuration schema with defensive logging."""
    try:
        return main_config_schema(user_input=user_input, hass=hass)
    except Exception as exc:  # pragma: no cover - safety net for unexpected schema issues
        _LOGGER.exception(
            "[config_flow][schema] Failed to build map schema (user_input=%s, hass_available=%s)",
            user_input,
            hass is not None,
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
    
    # Convert radius to meters for the location selector (it uses meters)
    radius_meters = int(radius_km * 1000)

    return vol.Schema(
        {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),  # 5 minutes to 24 hours
            vol.Required(
                CONF_RADIUS, 
                default=radius_miles
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),  # 0.5 to 31 miles (roughly 1-50 km)
            vol.Required(
                CONF_LOCATION,
                default=user_input.get(CONF_LOCATION, default_location),
            ): selector({
                "location": {
                    "radius": radius_meters,
                    "icon": "mdi:gas-station"
                }
            }),
            vol.Required(
                CONF_FUELTYPES,
                default=user_input.get(CONF_FUELTYPES, ["E10", "B7"]),
            ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
        }
    )


class FuelPricesUKFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Fuel Prices UK."""

    VERSION = SCHEMA_VERSION
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}
        self._data = {}
        self._location_method = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step - choose location input method."""
        _LOGGER.debug("[config_flow][step_user] Started - choosing location method")
        
        if user_input is not None:
            self._location_method = user_input[CONF_LOCATION_METHOD]
            _LOGGER.debug("[config_flow][step_user] Selected method: %s", self._location_method)
            
            if self._location_method == "map":
                return await self.async_step_location_map()
            else:
                return await self.async_step_location_address()
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCATION_METHOD, default="map"): vol.In({
                    "map": "Map (select on map)",
                    "address": "Address or Postcode (text input)"
                })
            }),
            description_placeholders={
                "info": "Choose how you want to specify your location."
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
                CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                CONF_LOCATION: {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                CONF_LOCATION_METHOD: "map",
                CONF_RADIUS: radius_km,  # Store in km
                CONF_FUELTYPES: user_input[CONF_FUELTYPES],
                CONF_STATIONS: [],  # Will be populated with actual stations during runtime
            }

            # Create a descriptive title (show in miles)
            location = user_input[CONF_LOCATION]
            title = f"{ENTRY_TITLE} - {radius_miles}mi radius"
            
            return self.async_create_entry(title=title, data=self._data)

        except InvalidUpdateInterval:
            self._errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
        except InvalidRadius:
            self._errors[CONF_RADIUS] = "invalid_radius"
        except NoFuelTypeSelected:
            self._errors[CONF_FUELTYPES] = "no_fuel_type_selected"
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
                data_schema=vol.Schema({
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=DEFAULT_UPDATE_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Required(
                        CONF_RADIUS,
                        default=default_radius
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),
                    vol.Required(CONF_ADDRESS): cv.string,
                    vol.Required(
                        CONF_FUELTYPES,
                        default=["E10", "B7"],
                    ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
                }),
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
                CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                CONF_LOCATION: {
                    "latitude": lat,
                    "longitude": lon,
                },
                CONF_LOCATION_METHOD: "address",
                CONF_ADDRESS: address,  # Store original address for reference
                CONF_RADIUS: radius_km,  # Store in km
                CONF_FUELTYPES: user_input[CONF_FUELTYPES],
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
        except InvalidAddress:
            self._errors[CONF_ADDRESS] = "invalid_address"
        except Exception as e:
            _LOGGER.exception("Unexpected error during address lookup: %s", e)
            self._errors["base"] = "unknown"

        return self.async_show_form(
            step_id="location_address",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                vol.Required(
                    CONF_RADIUS,
                    default=user_input.get(CONF_RADIUS, 3.0)
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),
                vol.Required(CONF_ADDRESS, default=user_input.get(CONF_ADDRESS, "")): cv.string,
                vol.Required(
                    CONF_FUELTYPES,
                    default=user_input.get(CONF_FUELTYPES, ["E10", "B7"]),
                ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
            }),
            errors=self._errors,
        )

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

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Manage the options - choose location method."""
        # Get current location method (default to map if not set for backwards compatibility)
        current_method = self.config_entry.data.get(CONF_LOCATION_METHOD, "map")
        
        if user_input is not None:
            if user_input[CONF_LOCATION_METHOD] == "map":
                return await self.async_step_location_map()
            else:
                return await self.async_step_location_address()
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCATION_METHOD, default=current_method): vol.In({
                    "map": "Map (select on map)",
                    "address": "Address or Postcode (text input)"
                })
            }),
            description_placeholders={
                "info": "Choose how you want to update your location."
            },
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
                updated_data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
                updated_data[CONF_LOCATION] = {
                    "latitude": latitude,
                    "longitude": longitude,
                }
                updated_data[CONF_LOCATION_METHOD] = "map"
                updated_data[CONF_RADIUS] = radius_km
                updated_data[CONF_FUELTYPES] = user_input[CONF_FUELTYPES]

                # Remove address if it was set before
                if CONF_ADDRESS in updated_data:
                    del updated_data[CONF_ADDRESS]

                return self.async_create_entry(title="", data=updated_data)
        
        # Get current radius in miles (stored in km, convert for display)
        radius_km = self.config_entry.data.get(CONF_RADIUS, 5)
        radius_miles = round(radius_km * KM_TO_MILES, 1)
        radius_meters = int(radius_km * 1000)

        return self.async_show_form(
            step_id="location_map",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Required(
                        CONF_RADIUS,
                        default=radius_miles,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),  # 0.5 to 31 miles
                    vol.Required(
                        CONF_LOCATION,
                        default=self.config_entry.data.get(CONF_LOCATION),
                    ): selector({
                        "location": {
                            "radius": radius_meters,
                            "icon": "mdi:gas-station"
                        }
                    }),
                    vol.Required(
                        CONF_FUELTYPES,
                        default=self.config_entry.data.get(CONF_FUELTYPES, ["E10", "B7"]),
                    ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
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

                # Convert address/postcode to coordinates
                address = user_input[CONF_ADDRESS]
                _LOGGER.debug("[options_flow][step_location_address] Looking up: %s", address)
                
                lat, lon = await self.hass.async_add_executor_job(get_lat_lon, address)
                
                if lat is None or lon is None:
                    _LOGGER.warning("[options_flow][step_location_address] Could not find location for: %s", address)
                    raise InvalidAddress("Could not find location. Please check your postcode/address and try again.")
                
                _LOGGER.info("[options_flow][step_location_address] Found coordinates: %s, %s for '%s'", lat, lon, address)

                # Convert radius from miles to km for storage
                radius_miles = user_input[CONF_RADIUS]
                radius_km = round(radius_miles * MILES_TO_KM, 1)

                # Preserve existing data and update with new values
                updated_data = dict(self.config_entry.data)
                updated_data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
                updated_data[CONF_LOCATION] = {
                    "latitude": lat,
                    "longitude": lon,
                }
                updated_data[CONF_LOCATION_METHOD] = "address"
                updated_data[CONF_ADDRESS] = address
                updated_data[CONF_RADIUS] = radius_km
                updated_data[CONF_FUELTYPES] = user_input[CONF_FUELTYPES]
                
                return self.async_create_entry(title="", data=updated_data)

            except InvalidUpdateInterval:
                self._errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
            except InvalidRadius:
                self._errors[CONF_RADIUS] = "invalid_radius"
            except NoFuelTypeSelected:
                self._errors[CONF_FUELTYPES] = "no_fuel_type_selected"
            except InvalidAddress:
                self._errors[CONF_ADDRESS] = "invalid_address"
            except Exception as e:
                _LOGGER.exception(
                    "[options_flow][step_location_address] Unexpected exception (raw=%r, user_input=%s)",
                    e,
                    user_input,
                )
                self._errors["base"] = "unknown"
        
        # Get current values
        radius_km = self.config_entry.data.get(CONF_RADIUS, 5)
        radius_miles = round(radius_km * KM_TO_MILES, 1)
        current_address = self.config_entry.data.get(CONF_ADDRESS, "")

        return self.async_show_form(
            step_id="location_address",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=user_input.get(CONF_UPDATE_INTERVAL, self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)) if user_input else self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                vol.Required(
                    CONF_RADIUS,
                    default=user_input.get(CONF_RADIUS, radius_miles) if user_input else radius_miles
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=31)),
                vol.Required(
                    CONF_ADDRESS,
                    default=user_input.get(CONF_ADDRESS, current_address) if user_input else current_address
                ): cv.string,
                vol.Required(
                    CONF_FUELTYPES,
                    default=user_input.get(CONF_FUELTYPES, self.config_entry.data.get(CONF_FUELTYPES, ["E10", "B7"])) if user_input else self.config_entry.data.get(CONF_FUELTYPES, ["E10", "B7"]),
                ): cv.multi_select({ft["value"]: ft["label"] for ft in FUEL_TYPES}),
            }),
            errors=self._errors,
        )


class InvalidRadius(HomeAssistantError):
    """Error to indicate an invalid radius."""


class InvalidUpdateInterval(HomeAssistantError):
    """Error to indicate the update interval is invalid."""


class NoFuelTypeSelected(HomeAssistantError):
    """Error to indicate no fuel type was selected."""


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
