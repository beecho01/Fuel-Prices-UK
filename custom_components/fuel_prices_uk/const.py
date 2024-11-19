DOMAIN = "fuel_prices_uk"
SCHEMA_VERSION = 1

CONF_UPDATE_INTERVAL = "update_interval"
CONF_STATIONS = "stations"
CONF_FUELTYPES = "fuel_types"

ATTR_LAST_UPDATED = "last_updated"
ATTR_RETAILER = "retailer"
ATTR_FUEL_TYPES = "fuel_types"

INTEGRATION_ID = "id"
NAME = "name"
ENTRY_TITLE = "Fuel Prices"
PLACEHOLDER_KEY_STATION_NAME = "station_name"
DEFAULT_UPDATE_INTERVAL = 60

DATA_STATION_APPLEGREEN = "Applegreen"
DATA_STATION_APPLEGREEN_URL = "https://applegreenstores.com/fuel-prices/data.json"
DATA_APPLEGREEN_FUEL_TYPES = [
    { "name": "B7", "unit": "l" },
    { "name": "SDV", "unit": "l" },
    { "name": "E5", "unit": "l" },
    { "name": "E10", "unit": "l" }
]

DATA_STATION_ASCONA_GROUP = "Ascona Group"
DATA_STATION_ASCONA_GROUP_URL = "https://fuelprices.asconagroup.co.uk/newfuel.json"
DATA_ASCONA_GROUP_FUEL_TYPES = [
    { "name": "B7", "unit": "l" },
    { "name": "E10", "unit": "l" }
]

DATA_STATION_ASDA = "Asda"
DATA_STATION_ASDA_URL = "https://storelocator.asda.com/fuel_prices_data.json"
DATA_ASDA_FUEL_TYPES = [
    { "name": "E10", "unit": "l" },
    { "name": "E5", "unit": "l" },
    { "name": "B7", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_BP = "BP"
DATA_STATION_BP_URL = "https://www.bp.com/en_gb/united-kingdom/home/fuelprices/fuel_prices_data.json"
DATA_BP_FUEL_TYPES = [
    { "name": "E5", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "B7", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_ESSO_TESCO_ALLIANCE = "Esso/Tesco Alliance"
DATA_STATION_ESSO_TESCO_ALLIANCE_URL = "https://fuelprices.esso.co.uk/latestdata.json"
DATA_ESSO_TESCO_ALLIANCE_FUEL_TYPES = [
    { "name": "B7", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "E5", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_JET = "Jet"
DATA_STATION_JET_URL = "https://jetlocal.co.uk/fuel_prices_data.json"
DATA_JET_FUEL_TYPES = [
    { "name": "E5", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "B7", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_KARAN = "Karan"
DATA_STATION_KARAN_URL = "https://api2.krlmedia.com/integration/live_price/krl"
DATA_KARAN_FUEL_TYPES = [
    { "name": "B7", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "E5", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_MORRISONS = "Morrisons"
DATA_STATION_MORRISONS_URL = "https://www.morrisons.com/fuel-prices/fuel.json"
DATA_MORRISONS_FUEL_TYPES = [
    { "name": "E10", "unit": "l" },
    { "name": "B7", "unit": "l" },
    { "name": "E5", "unit": "l" }
]

DATA_STATION_MOTO = "Moto Way"
DATA_STATION_MOTO_URL = "https://moto-way.com/fuel-price/fuel_prices.json"
DATA_MOTO_FUEL_TYPES = [
    { "name": "E5", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "B7", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_MOTOR_FUEL_GROUP = "Motor Fuel Group"
DATA_STATION_MOTOR_FUEL_GROUP_URL = "https://fuel.motorfuelgroup.com/fuel_prices_data.json"
DATA_MOTOR_FUEL_GROUP_FUEL_TYPES = [
    { "name": "E10", "unit": "l" },
    { "name": "E5", "unit": "l" },
    { "name": "B7", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_RONTEC = "Rontec"
DATA_STATION_RONTEC_URL = "https://www.rontec-servicestations.co.uk/fuel-prices/data/fuel_prices_data.json"
DATA_RONTEC_FUEL_TYPES = [
    { "name": "E5", "unit": "l" },
    { "name": "SDV", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "B7", "unit": "l" }
]

DATA_STATION_SAINSBURYS = "Sainsbury's"
DATA_STATION_SAINSBURYS_URL = "https://api.sainsburys.co.uk/v1/exports/latest/fuel_prices_data.json"
DATA_SAINSBURYS_FUEL_TYPES = [
    { "name": "E10", "unit": "l" },
    { "name": "E5", "unit": "l" },
    { "name": "B7", "unit": "l" }
]

DATA_STATION_SGN = "SGN"
DATA_STATION_SGN_URL = "https://www.sgnretail.uk/files/data/SGN_daily_fuel_prices.json"
DATA_SGN_FUEL_TYPES = [
    { "name": "E5", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "B7", "unit": "l" },
    { "name": "SDV", "unit": "l" }
]

DATA_STATION_SHELL = "Shell"
DATA_STATION_SHELL_URL = "https://www.shell.co.uk/fuel-prices-data.html"
DATA_SHELL_FUEL_TYPES = [
    { "name": "B7", "unit": "l" },
    { "name": "E10", "unit": "l" }
]

DATA_STATION_TESCO = "Tesco"
DATA_STATION_TESCO_URL = "https://www.tesco.com/fuel_prices/fuel_prices_data.json"
DATA_TESCO_FUEL_TYPES = [
    { "name": "E5", "unit": "l" },
    { "name": "E10", "unit": "l" },
    { "name": "B7", "unit": "l" }
]

DATA_STATIONS_NAME = sorted(
   [DATA_STATION_APPLEGREEN,
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
    DATA_STATION_TESCO]
)