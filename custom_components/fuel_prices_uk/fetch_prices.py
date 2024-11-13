import json, requests, subprocess

from fetch_retailers import fetch_fuel_retailers
from location import is_within_distance


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


def get_all_prices():
    price_data = []
    for retailer in fetch_fuel_retailers():
        name, url = retailer["retailer"], retailer["url"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
        }

        try:
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Error fetching {name} via requests: {e}, trying curl...")
            data = fetch_data_via_curl(name, url, headers)  # Tesco only allows curl commands

        if data:
            price_data.append({"retailer": name, "data": data})
        else:
            print(f"Failed to fetch data for {name} from {url}")

    return price_data


def nearby_prices(all_prices, latitude, longitude):
    nearby_stations = [
        {"query_location": {"latitude": latitude, "longitude": longitude}}
    ]
    for retailer in all_prices:
        name = retailer["retailer"]
        station_data = retailer["data"]
        filtered_stations = []
        for station in station_data["stations"]:
            station_latitude = station["location"]["latitude"]
            station_longitude = station["location"]["longitude"]
            if is_within_distance(
                {"latitude": latitude, "longitude": longitude},
                {"latitude": station_latitude, "longitude": station_longitude},
            ):
                filtered_stations.append(station)
        if filtered_stations:  # Remove retailer if no stations are nearby
            nearby_stations.append(
                {
                    "retailer": name,
                    "data": {
                        "last_updated": station_data["last_updated"],
                        "stations": filtered_stations,
                    },
                }
            )
    return nearby_stations
