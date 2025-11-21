"""Module to fetch fuel prices from UK government data feeds."""
import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import asyncio

if TYPE_CHECKING:
    from uk_fuel_prices_api import UKFuelPricesApi

try:
    from uk_fuel_prices_api import UKFuelPricesApi
    HAS_UK_FUEL_API = True
except ImportError:
    HAS_UK_FUEL_API = False
    UKFuelPricesApi = None  # type: ignore
    
from .location import is_within_distance

_LOGGER = logging.getLogger(__name__)


class UKFuelPricesClient:
    """Client for fetching UK fuel prices."""
    
    def __init__(self):
        """Initialize the UK Fuel Prices client."""
        if not HAS_UK_FUEL_API:
            raise ImportError("uk-fuel-prices-api is not installed")
        if UKFuelPricesApi is None:
            raise ImportError("uk-fuel-prices-api is not available")
        self.api = UKFuelPricesApi()
        self._prices_loaded = False
    
    async def initialize(self):
        """Initialize and fetch prices."""
        if not self._prices_loaded:
            _LOGGER.info("Initializing UK Fuel Prices API and fetching data")
            try:
                await self.api.get_prices()
                self._prices_loaded = True
                _LOGGER.info("Fuel prices data loaded successfully")
            except Exception as e:
                _LOGGER.error("Failed to initialize UK Fuel Prices API: %s", e, exc_info=True)
                raise
    
    async def search_stations(self, query: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Search for stations by name or location.
        
        Args:
            query: Search string
            limit: Maximum number of results to return
            
        Returns:
            List of matching stations
        """
        await self.initialize()
        results = await self.api.search(query, limit if limit is not None else 10)  # type: ignore[misc]
        return results if results else []
    
    async def get_station_by_id(self, site_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific station by its site ID.
        
        Args:
            site_id: The unique identifier for the station
            
        Returns:
            Station data or None if not found
        """
        await self.initialize()
        return await self.api.get_site_id(site_id)  # type: ignore[attr-defined]
    
    async def get_nearest_stations(self, latitude: float, longitude: float, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the nearest stations to a given location.
        
        Args:
            latitude: Latitude of the location
            longitude: Longitude of the location
            limit: Number of stations to return (default: 10)
            
        Returns:
            List of nearest stations with distance info
        """
        await self.initialize()
        stations = self.api.nearestN(latitude, longitude, limit)  # type: ignore[attr-defined]
        return stations if stations else []
    
    async def get_stations_within_radius(
        self, 
        latitude: float, 
        longitude: float, 
        radius_km: float
    ) -> List[Dict[str, Any]]:
        """
        Get all stations within a specified radius.
        
        Args:
            latitude: Latitude of the center point
            longitude: Longitude of the center point
            radius_km: Radius in kilometers
            
        Returns:
            List of stations within the radius
        """
        await self.initialize()
        stations = self.api.stationsWithinRadius(latitude, longitude, radius_km)  # type: ignore[attr-defined]
        return stations if stations else []
    
    def sort_by_fuel_price(
        self, 
        stations: List[Dict[str, Any]], 
        fuel_type: str
    ) -> List[Dict[str, Any]]:
        """
        Sort stations by fuel price.
        
        Args:
            stations: List of station dictionaries
            fuel_type: Fuel type to sort by (E10, E5, B7, SDV)
            
        Returns:
            Sorted list of stations (cheapest first)
        """
        return self.api.sortByPrice(stations, fuel_type)  # type: ignore[attr-defined]


async def get_uk_fuel_client() -> UKFuelPricesClient:
    """Get or create the UK Fuel Prices client."""
    return UKFuelPricesClient()


async def fetch_stations_by_criteria(
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
        client = await get_uk_fuel_client()
        
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
            stations = await client.get_stations_within_radius(
                latitude, longitude, radius_km
            )
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