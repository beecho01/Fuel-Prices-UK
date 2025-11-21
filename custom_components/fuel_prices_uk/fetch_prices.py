"""Module to fetch fuel prices from UK government data feeds."""
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from .api_client import FuelPricesAPI

_LOGGER = logging.getLogger(__name__)


async def fetch_stations_by_criteria(
    client: FuelPricesAPI,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: float = 5,
    site_id: Optional[str] = None,
    search_query: Optional[str] = None,
    fuel_types: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Fetch stations based on various criteria.
    
    Args:
        latitude: Latitude for location-based search
        longitude: Longitude for location-based search
        radius_km: Search radius in kilometers
        site_id: Specific station ID to fetch
        search_query: Text search query
        fuel_types: List of fuel types to filter by
        
    Returns:
        List of matching stations with price data
    """
    try:
        _LOGGER.debug(
            "fetch_stations_by_criteria called with: lat=%s, lon=%s, radius=%s, site_id=%s, query=%s, fuel_types=%s",
            latitude, longitude, radius_km, site_id, search_query, fuel_types
        )
        
        # Specific station lookup
        if site_id:
            _LOGGER.debug("Fetching station by site_id: %s", site_id)
            station = await client.get_station_by_id(site_id)
            result = [station] if station else []
            _LOGGER.debug("Site ID lookup returned %s stations", len(result))
            return result
        
        # Search by query
        if search_query:
            _LOGGER.debug("Searching stations by query: %s", search_query)
            results = await client.search_stations(search_query)
            _LOGGER.debug("Search query returned %s stations", len(results))
            return results
        
        # Location-based search
        if latitude is not None and longitude is not None:
            _LOGGER.debug("Getting stations within %s km of (%s, %s)", radius_km, latitude, longitude)
            stations = await client.get_stations_within_radius(latitude, longitude, radius_km)
            _LOGGER.debug("Found %s stations within radius", len(stations))
            
            # Filter and sort by fuel types if specified
            if fuel_types and stations:
                _LOGGER.debug("Filtering and sorting by fuel types: %s", fuel_types)
                filtered_stations = []
                for fuel_type in fuel_types:
                    try:
                        sorted_stations = client.sort_by_fuel_price(stations, fuel_type)
                        _LOGGER.debug("Sorted %s stations by %s price", len(sorted_stations), fuel_type)
                        filtered_stations.extend(sorted_stations)
                    except Exception as e:
                        _LOGGER.warning("Could not sort by fuel type %s: %s", fuel_type, e)
                
                # Remove duplicates while preserving order
                seen = set()
                unique_stations = []
                for station in filtered_stations:
                    station_id = station.get('id') or station.get('site_id')
                    if station_id and station_id not in seen:
                        seen.add(station_id)
                        unique_stations.append(station)
                
                _LOGGER.debug("After deduplication: %s unique stations", len(unique_stations))
                return unique_stations if unique_stations else stations
            
            return stations
        
        _LOGGER.warning("No valid search criteria provided to fetch_stations_by_criteria")
        return []
        
    except Exception as e:
        _LOGGER.error("Error fetching stations: %s", e, exc_info=True)
        raise  # Re-raise the exception so coordinator can handle it properly