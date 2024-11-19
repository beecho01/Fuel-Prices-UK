import requests
import logging
import json

from typing import List, Dict, Any, Optional
from .location import is_within_distance

from .const import (
    DATA_STATION_APPLEGREEN,
    DATA_STATION_APPLEGREEN_URL,
    DATA_STATION_ASCONA_GROUP,
    DATA_STATION_ASCONA_GROUP_URL,
    DATA_STATION_ASDA,
    DATA_STATION_ASDA_URL,
    DATA_STATION_BP,
    DATA_STATION_BP_URL,
    DATA_STATION_ESSO_TESCO_ALLIANCE,
    DATA_STATION_ESSO_TESCO_ALLIANCE_URL,
    DATA_STATION_JET,
    DATA_STATION_JET_URL,
    DATA_STATION_KARAN,
    DATA_STATION_KARAN_URL,
    DATA_STATION_MORRISONS,
    DATA_STATION_MORRISONS_URL,
    DATA_STATION_MOTO,
    DATA_STATION_MOTO_URL,
    DATA_STATION_MOTOR_FUEL_GROUP,
    DATA_STATION_MOTOR_FUEL_GROUP_URL,
    DATA_STATION_RONTEC,
    DATA_STATION_RONTEC_URL,
    DATA_STATION_SAINSBURYS,
    DATA_STATION_SAINSBURYS_URL,
    DATA_STATION_SGN,
    DATA_STATION_SGN_URL,
    DATA_STATION_SHELL,
    DATA_STATION_SHELL_URL,
    DATA_STATION_TESCO,
    DATA_STATION_TESCO_URL,
)

_LOGGER = logging.getLogger(__name__)

def get_all_prices() -> List[Dict[str, Any]]:
    """Fetch fuel prices from all configured stations."""
    stations = [
        {
            "name": DATA_STATION_APPLEGREEN,
            "url": DATA_STATION_APPLEGREEN_URL
        },
        {
            "name": DATA_STATION_ASCONA_GROUP,
            "url": DATA_STATION_ASCONA_GROUP_URL
        },
        {
            "name": DATA_STATION_ASDA,
            "url": DATA_STATION_ASDA_URL
        },
        {
            "name": DATA_STATION_BP,
            "url": DATA_STATION_BP_URL},
        {
            "name": DATA_STATION_ESSO_TESCO_ALLIANCE,
            "url": DATA_STATION_ESSO_TESCO_ALLIANCE_URL,
        },
        {
            "name": DATA_STATION_JET,
            "url": DATA_STATION_JET_URL
        },
        {
            "name": DATA_STATION_KARAN, 
            "url": DATA_STATION_KARAN_URL
        },
        {
            "name": DATA_STATION_MORRISONS,
            "url": DATA_STATION_MORRISONS_URL
        },
        {
            "name": DATA_STATION_MOTO,
            "url": DATA_STATION_MOTO_URL
        },
        {
            "name": DATA_STATION_MOTOR_FUEL_GROUP,
            "url": DATA_STATION_MOTOR_FUEL_GROUP_URL,
        },
        {
            "name": DATA_STATION_RONTEC,
            "url": DATA_STATION_RONTEC_URL
        },
        {   "name": DATA_STATION_SAINSBURYS,
            "url": DATA_STATION_SAINSBURYS_URL
        },
        {
            "name": DATA_STATION_SGN,
            "url": DATA_STATION_SGN_URL
        },
        {
            "name": DATA_STATION_SHELL,
            "url": DATA_STATION_SHELL_URL
        },
        {
            "name": DATA_STATION_TESCO,
            "url": DATA_STATION_TESCO_URL
        },
    ]

    all_prices = []

    for station in stations:
        station_name = station.get("name")
        station_url = station.get("url")

        if not station_name or not station_url:
            _LOGGER.error(f"Station information is incomplete: {station}")
            continue

        data = get_prices_from_station(station_name, station_url)
        if data:
            processed_data = process_station_data(station_name, data)
            if processed_data:
                all_prices.extend(processed_data)
        else:
            _LOGGER.warning(f"No data returned for {station_name}")

    return all_prices

def get_prices_from_station(station_name: str, station_url: str) -> Optional[Dict[str, Any]]:
    """Fetch prices from a single station."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; FuelPricesIntegration/1.0)'
        }
        response = requests.get(station_url, headers=headers, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        content_disposition = response.headers.get('Content-Disposition', '')

        _LOGGER.debug(f"Content type for {station_name}: {content_type}")
        _LOGGER.debug(f"Content disposition for {station_name}: {content_disposition}")

        if 'attachment' in content_disposition or 'application/octet-stream' in content_type:
            # Handle as file attachment
            try:
                content = response.content.decode('utf-8')
                data = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                _LOGGER.error(f"Failed to parse JSON data for {station_name}: {e}")
                return None
        else:
            # Attempt to parse the response as JSON directly
            try:
                data = response.json()
            except ValueError as e:
                _LOGGER.error(f"Failed to parse JSON data for {station_name}: {e}")
                return None

        return data

    except requests.exceptions.RequestException as e:
        _LOGGER.error(f"Error fetching data for {station_name}: {e}")
        return None

def process_station_data(station_name: str, data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Process raw data from a station and extract fuel prices."""
    try:
        prices = []

        if station_name == DATA_STATION_SAINSBURYS:
            # Existing processing logic for Sainsbury's
            for station in data.get('stations', []):
                station_address = station.get('address', 'Unknown')
                station_prices = station.get('prices', {})
                for fuel_type, price in station_prices.items():
                    prices.append({
                        'name': station_name,
                        'station_name': station_address,
                        'fuel_type': fuel_type,
                        'price': price,
                        'last_updated': data.get('last_updated'),
                    })

        elif station_name == DATA_STATION_SHELL:
            # Process data specific to Shell
            # Assuming Shell's data structure is similar
            for station in data.get('stations', []):
                station_address = station.get('address', 'Unknown')
                station_prices = station.get('prices', {})
                for fuel_type, price in station_prices.items():
                    prices.append({
                        'name': station_name,
                        'station_name': station_address,
                        'fuel_type': fuel_type,
                        'price': price,
                        'last_updated': data.get('last_updated'),
                    })

        # Add processing logic for other stations as needed

        else:
            # Default processing if applicable
            pass

        return prices if prices else None

    except Exception as e:
        _LOGGER.error(f"Error processing data for {station_name}: {e}")
        return None