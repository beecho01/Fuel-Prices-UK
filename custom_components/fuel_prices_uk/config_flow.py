import logging
import uuid
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SCHEMA_VERSION,
    CONF_UPDATE_INTERVAL,
    CONF_STATIONS,
    CONF_FUELTYPES,
    INTEGRATION_ID,
    ENTRY_TITLE,
    NAME,
    PLACEHOLDER_KEY_STATION_NAME,
    DATA_STATIONS_NAME,
    DATA_APPLEGREEN_FUEL_TYPES,
    DATA_ASCONA_GROUP_FUEL_TYPES,
    DATA_ASDA_FUEL_TYPES,
    DATA_BP_FUEL_TYPES,
    DATA_ESSO_TESCO_ALLIANCE_FUEL_TYPES,
    DATA_JET_FUEL_TYPES,
    DATA_KARAN_FUEL_TYPES,
    DATA_MORRISONS_FUEL_TYPES,
    DATA_MOTO_FUEL_TYPES,
    DATA_MOTOR_FUEL_GROUP_FUEL_TYPES,
    DATA_RONTEC_FUEL_TYPES,
    DATA_SAINSBURYS_FUEL_TYPES,
    DATA_SGN_FUEL_TYPES,
    DATA_SHELL_FUEL_TYPES,
    DATA_TESCO_FUEL_TYPES,
    DATA_STATION_APPLEGREEN,
    DATA_STATION_ASCONA_GROUP,
    DATA_STATION_ASDA,
    DATA_STATION_BP,
    DATA_STATION_ESSO_TESCO_ALLIANCE,
    DATA_STATION_JET,
    DATA_STATION_KARAN,
    DATA_STATION_MORRISONS,
    DATA_STATION_MOTO,
    DATA_STATION_MOTOR_FUEL_GROUP,
    DATA_STATION_RONTEC,
    DATA_STATION_SAINSBURYS,
    DATA_STATION_SGN,
    DATA_STATION_SHELL,
    DATA_STATION_TESCO,
)

_LOGGER = logging.getLogger(__name__)

async def validate_input_user(data: dict):
    """Validate input [STEP: user]."""
    if data[CONF_UPDATE_INTERVAL] < 60:
        raise InvalidUpdateInterval
    if len(data[CONF_STATIONS]) < 1:
        raise NoStationSelected
    return data

async def validate_input_station(data: dict):
    """Validate input [STEP: station]."""
    if len(data[CONF_FUELTYPES]) < 1:
        raise NoFuelTypeSelected
    return data

def main_config_schema(user_input=None):
    """Define the schema for the main configuration step."""
    if user_input is None:
        user_input = {}

    return vol.Schema({
        vol.Required(CONF_UPDATE_INTERVAL, default=user_input.get(CONF_UPDATE_INTERVAL, 60)): vol.All(vol.Coerce(int), vol.Range(min=60)),
        vol.Required(CONF_STATIONS, default=user_input.get(CONF_STATIONS, [])): cv.multi_select(DATA_STATIONS_NAME),
    })

def station_config_schema(station_name, user_input=None):
    """Define the schema for configuring each station."""
    if user_input is None:
        user_input = {}

    station_fuel_types = get_station_fuel_types(station_name)

    return vol.Schema({
        vol.Required(CONF_FUELTYPES, default=user_input.get(CONF_FUELTYPES, [])): cv.multi_select(station_fuel_types),
    })

def get_station_fuel_types(station_name):
    """Get the available fuel types for a given station."""
    station_fuel_types = {
        DATA_STATION_APPLEGREEN: [fuel['name'] for fuel in DATA_APPLEGREEN_FUEL_TYPES],
        DATA_STATION_ASCONA_GROUP: [fuel['name'] for fuel in DATA_ASCONA_GROUP_FUEL_TYPES],
        DATA_STATION_ASDA: [fuel['name'] for fuel in DATA_ASDA_FUEL_TYPES],
        DATA_STATION_BP: [fuel['name'] for fuel in DATA_BP_FUEL_TYPES],
        DATA_STATION_ESSO_TESCO_ALLIANCE: [fuel['name'] for fuel in DATA_ESSO_TESCO_ALLIANCE_FUEL_TYPES],
        DATA_STATION_JET: [fuel['name'] for fuel in DATA_JET_FUEL_TYPES],
        DATA_STATION_KARAN: [fuel['name'] for fuel in DATA_KARAN_FUEL_TYPES],
        DATA_STATION_MORRISONS: [fuel['name'] for fuel in DATA_MORRISONS_FUEL_TYPES],
        DATA_STATION_MOTO: [fuel['name'] for fuel in DATA_MOTO_FUEL_TYPES],
        DATA_STATION_MOTOR_FUEL_GROUP: [fuel['name'] for fuel in DATA_MOTOR_FUEL_GROUP_FUEL_TYPES],
        DATA_STATION_RONTEC: [fuel['name'] for fuel in DATA_RONTEC_FUEL_TYPES],
        DATA_STATION_SAINSBURYS: [fuel['name'] for fuel in DATA_SAINSBURYS_FUEL_TYPES],
        DATA_STATION_SGN: [fuel['name'] for fuel in DATA_SGN_FUEL_TYPES],
        DATA_STATION_SHELL: [fuel['name'] for fuel in DATA_SHELL_FUEL_TYPES],
        DATA_STATION_TESCO: [fuel['name'] for fuel in DATA_TESCO_FUEL_TYPES],
    }
    return station_fuel_types.get(station_name, [])

class FuelPricesUKFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Fuel Prices UK."""

    VERSION = SCHEMA_VERSION
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}
        self._data = {}
        self._current_station_index = 0
        self._stations = []

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        _LOGGER.debug("[config_flow][step_user] Started")
        self._errors = {}
        self._data = {}

        if user_input is None:
            _LOGGER.debug("[config_flow][step_user] No user input")
            return self.async_show_form(
                step_id="user",
                data_schema=main_config_schema(),
            )

        try:
            user_input = await validate_input_user(user_input)
        except InvalidUpdateInterval:
            self._errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
            _LOGGER.debug("[config_flow][step_user] Invalid update interval")
            return self.async_show_form(
                step_id="user",
                data_schema=main_config_schema(user_input),
                errors=self._errors,
            )
        except NoStationSelected:
            self._errors[CONF_STATIONS] = "no_station_selected"
            _LOGGER.debug("[config_flow][step_user] No station selected")
            return self.async_show_form(
                step_id="user",
                data_schema=main_config_schema(user_input),
                errors=self._errors,
            )

        integration_id = str(uuid.uuid4())
        await self.async_set_unique_id(integration_id)
        self._data[INTEGRATION_ID] = integration_id
        self._data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
        self._stations = user_input[CONF_STATIONS]
        self._data[CONF_STATIONS] = [{NAME: name, CONF_FUELTYPES: []} for name in self._stations]
        self._current_station_index = 0

        return await self.async_step_station()

    async def async_step_station(self, user_input=None):
        """Station configuration step."""
        _LOGGER.debug("[config_flow][step_station] Started")
        self._errors = {}
        last_step = self.check_last_step()
        current_station = self.get_current_station()
        placeholders = {PLACEHOLDER_KEY_STATION_NAME: current_station}

        if user_input is not None:
            try:
                user_input = await validate_input_station(user_input)
            except NoFuelTypeSelected:
                self._errors[CONF_FUELTYPES] = "no_fuel_type_selected"
                _LOGGER.debug("[config_flow][step_station] No fuel type selected")
                return self.async_show_form(
                    step_id="station",
                    data_schema=station_config_schema(current_station, user_input),
                    errors=self._errors,
                    description_placeholders=placeholders,
                )
            station_index = self.get_station_index(current_station)
            self._data[CONF_STATIONS][station_index][CONF_FUELTYPES] = user_input[CONF_FUELTYPES]

            if not last_step:
                self._current_station_index += 1
                return await self.async_step_station()

            entry_result = self.async_create_entry(title=ENTRY_TITLE, data=self._data)
            _LOGGER.debug("[config_flow][step_station] Entry created.")
            return entry_result

        return self.async_show_form(
            step_id="station",
            data_schema=station_config_schema(current_station),
            errors=self._errors,
            description_placeholders=placeholders,
        )

    def check_last_step(self):
        """Check if this is the last step."""
        return self._current_station_index >= len(self._stations) - 1

    def get_current_station(self):
        """Get the current station being configured."""
        return self._stations[self._current_station_index]

    def get_station_index(self, station_name):
        """Get the index of the station in the data list."""
        for index, station in enumerate(self._data[CONF_STATIONS]):
            if station[NAME] == station_name:
                return index
        return None

class InvalidUpdateInterval(HomeAssistantError):
    """Error to indicate the update interval is invalid."""

class NoStationSelected(HomeAssistantError):
    """Error to indicate no station was selected."""

class NoFuelTypeSelected(HomeAssistantError):
    """Error to indicate no fuel type was selected."""