import json, requests, subprocess, logging

from fetch_retailers import fetch_fuel_retailers
from location import is_within_distance

_LOGGER = logging.getLogger(__name__)

#Fetching Data with Requests and Fallback to Curl
def fetch_data_via_curl(name, url, headers):
    try:
        command = [
            'curl', '-s', url,
            '-H', 'accept-language: en-GB,en;q=0.9',
            '-H', f"User-Agent: {headers['User-Agent']}",
            '--compressed'
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        return json.loads(result.stdout) if result.returncode == 0 else None
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error fetching {name} via curl: {e}")
        return None

#Fetching Data from All Retailers
def get_all_prices():
    price_data = []
    session = requests.Session()
    for retailer in fetch_fuel_retailers():
        name, url = retailer["retailer"], retailer["url"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
        }

    for retailer in fetch_fuel_retailers():
        name, url = retailer["retailer"], retailer["url"]
        try:
            response = session.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            _LOGGER.error(f"HTTP error fetching {name}: {e}")
            data = None
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Request exception fetching {name}: {e}")
            data = None
        except json.JSONDecodeError as e:
            _LOGGER.error(f"JSON decode error fetching {name}: {e}")
            data = None

        if data:
            price_data.append({"retailer": name, "data": data})
        else:
            _LOGGER.warning(f"Failed to fetch data for {name} from {url}")

    return price_data

#Filtering Nearby Fuel Stations
def nearby_prices(all_prices, latitude, longitude, radius=5, unit='km'):
    nearby_stations = [
        {"query_location": {"latitude": latitude, "longitude": longitude}}
    ]
    for retailer in all_prices:
        name = retailer["retailer"]
        station_data = retailer["data"]
        filtered_stations = []
        for station in station_data.get("stations", []):
            station_latitude = station["location"]["latitude"]
            station_longitude = station["location"]["longitude"]
            if is_within_distance(
                {"latitude": latitude, "longitude": longitude},
                {"latitude": station_latitude, "longitude": station_longitude},
                radius,
                unit
            ):
                filtered_stations.append(station)
        if filtered_stations:
            nearby_stations.append(
                {
                    "retailer": name,
                    "data": {
                        "last_updated": station_data.get("last_updated"),
                        "stations": filtered_stations,
                    },
                }
            )
    return nearby_stations

# Test Code
#from fetch_prices import get_all_prices, nearby_prices
#
#def main():
    # Fetch all fuel prices
#    all_prices = get_all_prices()

    # Coordinates for the City of London
#    city_of_london_latitude = 51.5074
#    city_of_london_longitude = -0.1278

    # Define the radius and units
#    radius = float(input("Enter the search radius: "))
#    unit = input("Enter the unit ('km' or 'mi'): ").strip().lower()

#    if unit not in ['km', 'mi']:
#        print("Invalid unit. Defaulting to kilometers.")
#        unit = 'mi'

    # Get nearby stations
#    nearby_stations = nearby_prices(
#        all_prices,
#        city_of_london_latitude,
#        city_of_london_longitude,
#        radius=radius,
#        unit=unit
#    )

    # Print the results
#    for retailer in nearby_stations:
#        if 'query_location' in retailer:
#            continue  # Skip the query location entry
#        print(f"Retailer: {retailer['retailer']}")
#        for station in retailer['data']['stations']:
#            station_name = station.get('name', 'Unknown')
#            station_lat = station['location']['latitude']
#            station_lon = station['location']['longitude']
#            print(f"  Station: {station_name}")
#            print(f"    Location: ({station_lat}, {station_lon})")
#            print(f"    Prices: {station.get('prices', {})}")
#            print(f"    Last Updated: {station.get('last_updated', 'N/A')}")
#        print("\n")

#if __name__ == "__main__":
#    main()