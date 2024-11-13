"""UK Fuel Price API"""

import asyncio
import aiohttp
import logging
from dataclasses import dataclass
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from typing import Optional, List, Dict, Any
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from .const import ALL_ENDPOINTS, FUEL_TYPES

_LOGGER = logging.getLogger(__name__)

@dataclass
class Location:
    """Location data structure."""
    latitude: float
    longitude: float

@dataclass
class FuelPrices:
    """Fuel prices data structure."""
    B7: Optional[float] = None
    E10: Optional[float] = None
    E5: Optional[float] = None
    SDV: Optional[float] = None

@dataclass
class Station:
    """Fuel station data structure."""
    site_id: str
    brand: str
    address: str
    postcode: str
    location: Location
    prices: FuelPrices
    last_updated: datetime

class UKFuelPricesApi:
    """UK Fuel Prices API with improved error handling and caching."""

    def __init__(self) -> None:
        """Initialize UK Fuel Price API."""
        self.stations = pd.DataFrame()
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache_timestamp: Optional[datetime] = None
        self.cache_duration = 3600  # Cache duration in seconds

    async def __aenter__(self):
        """Async context manager enter."""
        await self.__open_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.__close_session()

    async def __get_endpoint_dataframe(self, endpoint: str) -> Optional[pd.DataFrame]:
        """Fetch data from a single endpoint with improved error handling."""
        try:
            async with self.session.get(endpoint) as response:
                if response.status != 200:
                    _LOGGER.error("Error fetching %s: HTTP %d", endpoint, response.status)
                    return None
                
                json = await response.json(content_type=None)
                if not json.get("stations"):
                    _LOGGER.warning("No stations data in response from %s", endpoint)
                    return None

                stations = pd.DataFrame.from_dict(json["stations"])
                
                # Parse the last_updated field with explicit format and dayfirst=True
                try:
                    stations["last_updated"] = pd.to_datetime(
                        json["last_updated"],
                        format="%d/%m/%Y %H:%M:%S",
                        dayfirst=True
                    )
                except ValueError as e:
                    _LOGGER.warning("Date parsing error for %s: %s. Trying flexible parser.", endpoint, str(e))
                    # Fallback to flexible parser if the format doesn't match
                    stations["last_updated"] = pd.to_datetime(
                        json["last_updated"],
                        dayfirst=True,
                        format='mixed'
                    )

                stations["source_endpoint"] = endpoint

                # Normalize nested JSON columns
                for column in ["location", "prices"]:
                    if column in stations.columns:
                        normalized = pd.json_normalize(stations[column])
                        stations = stations.drop(column, axis=1)
                        stations = pd.concat([stations, normalized], axis=1)

                return stations

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching %s", endpoint)
        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching %s: %s", endpoint, str(e))
        except ValueError as e:
            _LOGGER.error("JSON parsing error for %s: %s", endpoint, str(e))
        except Exception as e:
            _LOGGER.error("Unexpected error fetching %s: %s", endpoint, str(e))
        
        return None

    async def get_prices(self, force_refresh: bool = False) -> bool:
        """Query all endpoints for fuel station prices with caching."""
        now = datetime.now()
        
        # Return cached data if it's still valid
        if not force_refresh and self._cache_timestamp:
            if (now - self._cache_timestamp).total_seconds() < self.cache_duration:
                return len(self.stations) > 0

        station_dfs = []
        
        async with self:  # Use context manager for session handling
            # Fetch all endpoints concurrently
            tasks = [self.__get_endpoint_dataframe(endpoint) for endpoint in ALL_ENDPOINTS]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for df in results:
                if isinstance(df, pd.DataFrame):
                    station_dfs.append(df)
                elif isinstance(df, Exception):
                    _LOGGER.error("Error fetching endpoint: %s", str(df))

        if not station_dfs:
            _LOGGER.error("No valid data retrieved from any endpoint")
            return False

        self.stations = pd.concat(station_dfs, ignore_index=True)
        
        # Convert data types
        self.stations["latitude"] = pd.to_numeric(self.stations["latitude"], errors="coerce")
        self.stations["longitude"] = pd.to_numeric(self.stations["longitude"], errors="coerce")
        
        # Remove invalid coordinates
        self.stations = self.stations.dropna(subset=["latitude", "longitude"])
        
        self.__correct_pence_to_pounds()
        self._cache_timestamp = now
        
        return len(self.stations) > 0

    def __correct_pence_to_pounds(self) -> None:
        """Correct any values returned in pence to pounds."""
        ASSUME_POUNDS_IF_OVER = 10
        
        for fuel_type in FUEL_TYPES.keys():
            if fuel_type in self.stations.columns:
                mask = self.stations[fuel_type] > ASSUME_POUNDS_IF_OVER
                self.stations.loc[mask, fuel_type] = self.stations.loc[mask, fuel_type] / 100

    def search(self, value: str, n: int = 10) -> List[Dict[str, Any]]:
        """Search stations with improved error handling."""
        try:
            if not value or not isinstance(value, str):
                raise ValueError("Invalid search value")

            search_columns = ["brand", "address", "postcode"]
            mask = self.stations[search_columns].apply(
                lambda x: x.str.contains(value, case=False, na=False)
            ).any(axis=1)

            return self.stations[mask].head(n).to_dict("records")
        except Exception as e:
            _LOGGER.error("Search error: %s", str(e))
            return []
        
    def get_station(self, station_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single station by its ID.
        
        Args:
            station_id: The unique identifier of the station to retrieve
            
        Returns:
            Optional[Dict[str, Any]]: Station data as a dictionary if found, None otherwise
            
        Raises:
            ValueError: If station_id is empty or invalid
        """
        try:
            if not station_id or not isinstance(station_id, str):
                raise ValueError("Invalid station ID provided")
                
            if self.stations.empty:
                _LOGGER.warning("No station data available. Call get_prices() first.")
                return None
                
            # Find the station by ID
            station_mask = self.stations["site_id"].str.lower() == station_id.lower()
            matching_stations = self.stations[station_mask]
            
            if matching_stations.empty:
                _LOGGER.debug("No station found with ID: %s", station_id)
                return None
                
            if len(matching_stations) > 1:
                _LOGGER.warning("Multiple stations found with ID %s, returning first match", station_id)
                
            # Convert the first matching station to a dictionary
            station_data = matching_stations.iloc[0].to_dict()
            
            # Format the last_updated timestamp if present
            if "last_updated" in station_data and pd.notnull(station_data["last_updated"]):
                station_data["last_updated"] = station_data["last_updated"].isoformat()
                
            # Round numeric values for cleaner output
            for key, value in station_data.items():
                if isinstance(value, float):
                    station_data[key] = round(value, 3)
                    
            return station_data
            
        except Exception as e:
            _LOGGER.error("Error retrieving station with ID %s: %s", station_id, str(e))
            return None

    @staticmethod
    def distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points on the Earth's surface 
        using the Haversine formula.
        
        Args:
            lat1: Latitude of the first point in decimal degrees
            lon1: Longitude of the first point in decimal degrees
            lat2: Latitude of the second point in decimal degrees
            lon2: Longitude of the second point in decimal degrees
            
        Returns:
            float: Distance between the points in kilometers, rounded to 2 decimal places
            
        Raises:
            ValueError: If any input coordinate is not a valid float, or if coordinates
                    are outside valid ranges (latitude: -90 to 90, longitude: -180 to 180)
        """
        try:
            # Convert inputs to float and validate they can be converted
            try:
                lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
            except (TypeError, ValueError) as e:
                raise ValueError("All coordinates must be valid numbers") from e
            
            # Validate coordinate ranges
            for lat in [lat1, lat2]:
                if not -90 <= lat <= 90:
                    raise ValueError(f"Invalid latitude {lat}. Must be between -90 and 90 degrees")
                    
            for lon in [lon1, lon2]:
                if not -180 <= lon <= 180:
                    raise ValueError(f"Invalid longitude {lon}. Must be between -180 and 180 degrees")
            
            # Convert decimal degrees to radians
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
            
            # Haversine formula
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            
            # Earth's radius in kilometers (mean radius = 6371 km)
            km = 6371 * c
            
            return round(km, 2)
            
        except Exception as e:
            _LOGGER.error("Distance calculation error: %s", str(e))
            raise ValueError(f"Error calculating distance: {str(e)}")

    def stationsWithinRadius(
        self, latitude: float, longitude: float, radiusInKm: float
    ) -> List[Dict[str, Any]]:
        """Find stations within radius with validation and optimization."""
        try:
            if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
                raise ValueError("Invalid coordinates")
            
            if not isinstance(radiusInKm, (int, float)) or radiusInKm <= 0:
                raise ValueError("Invalid radius")

            if self.stations.empty:
                return []

            # Convert inputs to float to ensure consistency
            lat = float(latitude)
            lon = float(longitude)
            radius = float(radiusInKm)

            # Use vectorized operations for better performance
            stations = self.stations.copy()
            
            # Calculate distances using vectorized operations
            stations['dist'] = stations.apply(
                lambda row: self.distance(lat, lon, 
                    float(row['latitude']), float(row['longitude'])),
                axis=1
            )
            
            # Filter stations within radius
            within_radius = stations[stations['dist'] <= radius].copy()
            
            if within_radius.empty:
                return []
            
            # Sort by distance
            within_radius = within_radius.sort_values('dist')
            
            # Convert to records and clean data
            results = []
            for record in within_radius.to_dict('records'):
                cleaned_record = {}
                for key, value in record.items():
                    if pd.isna(value):
                        cleaned_record[key] = None
                    elif isinstance(value, pd.Timestamp):
                        cleaned_record[key] = value.isoformat()
                    elif isinstance(value, float):
                        cleaned_record[key] = round(value, 6)
                    else:
                        cleaned_record[key] = value
                results.append(cleaned_record)
            
            return results
            
        except Exception as e:
            _LOGGER.error(f"Error finding stations within radius: {e}")
            return []

    async def __open_session(self) -> None:
        """Open aiohttp session with retry capability."""
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            },
        )

    async def __close_session(self) -> None:
        """Safely close aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()