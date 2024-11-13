import logging
import json
from pathlib import Path

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.typing import ConfigType
from uk_fuel_prices_api import UKFuelPricesApi
from .utils import check_settings, FuelType, ComponentSession

manifestfile = Path(__file__).parent / 'manifest.json'
with open(manifestfile, 'r') as json_file:
    manifest_data = json.load(json_file)

DOMAIN = manifest_data.get("domain")
NAME = manifest_data.get("name")
VERSION = manifest_data.get("version")
ISSUEURL = manifest_data.get("issue_tracker")
PLATFORMS = [Platform.SENSOR]

LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up this component using YAML."""
    LOGGER.info(STARTUP)
    if config.get(DOMAIN) is None:
        return True

    try:
        await hass.config_entries.async_forward_entry(config, Platform.SENSOR)
        LOGGER.info("Successfully added sensor from the integration")
    except ValueError:
        pass

    await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data={}
    )
    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    # if unload_ok:
        # hass.data[DOMAIN].pop(config_entry.entry_id)
    return unload_ok

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up component as config entry."""
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_update_options))
    LOGGER.info(f"{DOMAIN} register_services")
    register_services(hass, config_entry)
    return True

async def async_remove_entry(hass, config_entry):
    try:
        await hass.config_entries.async_forward_entry_unload(config_entry, Platform.SENSOR)
        LOGGER.info("Successfully removed sensor from the integration")
    except ValueError:
        pass

def register_services(hass, config_entry):
        
    async def handle_get_lowest_fuel_price(call):
        """Handle the service call."""
        fuel_type = getattr(FuelType, call.data.get('fuel_type').upper(), None)
        country = call.data.get('country')
        postalcode = call.data.get('postalcode')
        town = call.data.get('town','')
        if town is None:
            town = ""
        max_distance = call.data.get('max_distance')
        if max_distance is None:
            max_distance = 0
        filter = call.data.get('filter','')
        if filter is None:
            filter = ""        
        
        config = config_entry.data
        GEO_API_KEY = config.get("GEO_API_KEY")
        
        session = ComponentSession(GEO_API_KEY)
        station_info = await hass.async_add_executor_job(lambda: session.getStationInfo(postalcode, country, fuel_type, town, max_distance, filter, True))
        
        _LOGGER.debug(f"{NAME} get_lowest_fuel_price info found: {station_info}")
        hass.bus.async_fire(f"{DOMAIN}_lowest_fuel_price", station_info)