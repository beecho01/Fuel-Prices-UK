"""Location utilities for geocoding and coordinate validation."""
import json
import logging
from typing import Dict, Optional, Tuple

import requests
from geopy import distance
from geopy.exc import GeocoderUnavailable
from geopy.geocoders import Nominatim

_LOGGER = logging.getLogger(__name__)

def get_lat_lon(query: str) -> Tuple[Optional[float], Optional[float]]:
    query = query.strip()

    coordinates_check = is_coordinates(query)
    if all(coordinates_check):
        return coordinates_check

    postcode_check = is_postcode(query)
    if all(postcode_check):
        return postcode_check

    if len(query) >= 2:
        location_check = is_location(query)
        if all(location_check):
            return location_check

        geolocator = Nominatim(user_agent="UKFP")
        try:
            location = geolocator.geocode(query, country_codes="GB")
        except GeocoderUnavailable as geocode_err:
            _LOGGER.warning("Geocoder service unavailable: %s", geocode_err)
            return None, None

        if location:
            latitude = getattr(location, "latitude", None)
            longitude = getattr(location, "longitude", None)
            return latitude, longitude
        return None, None
    return None, None


def is_postcode(query: str) -> Tuple[Optional[float], Optional[float]]:
    url = f"https://api.postcodes.io/postcodes/{query}"
    result = fetch_postcode_data(url)

    if result:
        return result.get("latitude"), result.get("longitude")

    return None, None


def is_coordinates(query: str) -> Tuple[Optional[float], Optional[float]]:
    try:
        latitude, longitude = map(float, query.split(","))
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return latitude, longitude
    except (ValueError, TypeError):
        pass
    return None, None


def is_location(query: str) -> Tuple[Optional[float], Optional[float]]:
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


def rank_local_type(local_type: Optional[str]) -> int:
    priority = {
        "City": 1,
        "Town": 2,
        "Village": 3,
        "Suburban Area": 4,
        "Hamlet": 5,
        "Other Settlement": 6,
    }
    if not local_type:
        return 999
    return priority.get(local_type, 999)

def fetch_postcode_data(url: str) -> Optional[dict]:
    response = None
    try:
        response = requests.get(url)
        response.raise_for_status()
        response_json = response.json()
        return response_json.get("result")
    except requests.exceptions.HTTPError as http_err:
        if response and response.status_code == 404:
            _LOGGER.warning("Postcode - 404: Not Found")
        else:
            _LOGGER.error("Postcode - HTTP error occurred: %s", http_err)
    except requests.exceptions.RequestException as req_err:
        _LOGGER.error("Postcode - Request error occurred: %s", req_err)
    except json.JSONDecodeError as json_err:
        _LOGGER.error("Postcode - JSON decoding error occurred: %s", json_err)
    return None

def is_within_distance(user_location: Dict[str, float], station_location: Dict[str, float], radius: float = 5, unit: str = 'mi') -> bool:
    unit = unit.lower()
    if unit not in ('km', 'mi'):
        raise ValueError("Invalid unit. Please use 'km' or 'mi'.")

    user_coords = (user_location["latitude"], user_location["longitude"])
    station_coords = (station_location["latitude"], station_location["longitude"])
    calculated_distance = distance.distance(user_coords, station_coords)

    return (calculated_distance.km if unit == 'km' else calculated_distance.miles) <= radius