import requests

from geopy import distance
from geopy.exc import GeocoderUnavailable
from geopy.geocoders import Nominatim


def get_lat_lon(query):
    query = query.strip()

    coordinates_check = is_coordinates(query)
    if all(coordinates_check):
        return coordinates_check

    postcode_check = is_postcode(query)
    if all(postcode_check):
        return postcode_check

    if len(query) >= 2:
        # location_check = is_location(query)
        # if all(location_check):
        #     return location_check

        geolocator = Nominatim(user_agent="UKFP")
        try:
            location = geolocator.geocode(query, country_codes="GB")
        except GeocoderUnavailable as geocode_err:
            print(f"Geocoder service unavailable: {geocode_err}")
            return None, None

        if location:
            return location.latitude, location.longitude
        else:
            return None, None
    return None, None


def is_postcode(query):
    url = f"https://api.postcodes.io/postcodes/{query}"
    result = fetch_postcode_data(url)

    if result:
        return result.get("latitude"), result.get("longitude")

    return None, None


def is_coordinates(query):
    try:
        latitude, longitude = map(float, query.split(","))
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return latitude, longitude
    except (ValueError, TypeError):
        pass
    return None, None


def is_location(query):
    url = f"https://api.postcodes.io/places?limit=10&q={query}"
    results = fetch_postcode_data(url)

    if results:
        filtered_results = [
            result
            for result in results
            if result.get("name_1", "").lower() == query.lower()
        ]

        if not filtered_results:
            return None, None

        ranked_results = sorted(
            filtered_results, key=lambda r: rank_local_type(r.get("local_type"))
        )

        best_match = ranked_results[0]
        return best_match.get("latitude"), best_match.get("longitude")

    return None, None


def rank_local_type(local_type):
    priority = {
        "City": 1,
        "Town": 2,
        "Village": 3,
        "Suburban Area": 4,
        "Hamlet": 5,
        "Other Settlement": 6,
    }
    return priority.get(local_type, 999)


def fetch_postcode_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        response_json = response.json()

        return response_json.get("result")

    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            print("Postcode - 404: Not Found")
        else:
            print(f"Postcode - HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"Postcode - Request error occurred: {req_err}")
    except ValueError as json_err:
        print(f"Postcode - JSON decoding error occurred: {json_err}")

    return None


def is_within_distance(user_location, station_location, max_distance=5):
    user_coords = (user_location["latitude"], user_location["longitude"])
    station_coords = (station_location["latitude"], station_location["longitude"])

    return distance.distance(user_coords, station_coords).miles <= max_distance
