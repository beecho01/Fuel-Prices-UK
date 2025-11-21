"""Constants for the Fuel Prices UK integration."""

DOMAIN = "fuel_prices_uk"
SCHEMA_VERSION = 1

CONF_UPDATE_INTERVAL = "update_interval"
CONF_STATIONS = "stations"
CONF_FUELTYPES = "fuel_types"
CONF_LOCATION = "location"
CONF_LOCATION_METHOD = "location_method"
CONF_ADDRESS = "address"
CONF_RADIUS = "radius"
CONF_SEARCH_METHOD = "search_method"
CONF_SITE_ID = "site_id"

ATTR_LAST_UPDATED = "last_updated"
ATTR_RETAILER = "retailer"
ATTR_FUEL_TYPES = "fuel_types"
ATTR_STATION_NAME = "station_name"
ATTR_ADDRESS = "address"
ATTR_POSTCODE = "postcode"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_BRAND = "brand"
ATTR_DISTANCE = "distance"

INTEGRATION_ID = "id"
NAME = "name"
ENTRY_TITLE = "Fuel Prices UK"
PLACEHOLDER_KEY_STATION_NAME = "station_name"
DEFAULT_UPDATE_INTERVAL = 3600  # 1 hour in seconds

# Supported fuel types based on UK government data
FUEL_TYPE_E10 = "E10"
FUEL_TYPE_E5 = "E5"
FUEL_TYPE_B7 = "B7"
FUEL_TYPE_SDV = "SDV"

FUEL_TYPES = [
    {"value": FUEL_TYPE_E10, "label": "E10 (Unleaded Petrol)"},
    {"value": FUEL_TYPE_E5, "label": "E5 (Super Unleaded)"},
    {"value": FUEL_TYPE_B7, "label": "B7 (Diesel)"},
    {"value": FUEL_TYPE_SDV, "label": "SDV (Super Diesel)"},
]

# Conversion constants
MILES_TO_KM = 1.60934
KM_TO_MILES = 0.621371