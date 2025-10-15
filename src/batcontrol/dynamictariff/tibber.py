"""
Refactored Tibber Class using unified fetching infrastructure.

This module implements the Tibber API to retrieve dynamic electricity prices.
It inherits from the refactored DynamicTariffBaseclass.

Classes:
    TibberRefactored: A class to interact with the Tibber API using BaseFetcher infrastructure.

Methods:
    __init__(self, timezone, token: str, min_time_between_API_calls=900, delay_evaluation_by_seconds=0):
        Initializes the TibberRefactored class with the specified parameters.

    get_raw_data_from_provider(self):
        Fetches raw data from the Tibber API using unified HTTP client.

    get_prices_from_raw_data(self):
        Processes the raw data to extract electricity prices.
"""
import datetime
import math
from typing import Dict

from .baseclass import DynamicTariffBaseclass
from ..fetching.constants import EXTERNAL_REFRESH_INTERVAL


class Tibber(DynamicTariffBaseclass):
    """
    Refactored Tibber API implementation using unified fetching infrastructure.
    
    Inherits from DynamicTariffBaseclass (which extends BaseFetcher) to eliminate
    duplicated caching, delay, and error handling logic.
    """

    def __init__(
        self, 
        timezone,
        token: str, 
        min_time_between_API_calls: int = EXTERNAL_REFRESH_INTERVAL,  # Use constant (30 min)
        delay_evaluation_by_seconds: int = 30,  # Max 30s random delay
        **kwargs
    ):
        """
        Initialize Tibber provider.
        
        Args:
            timezone: Timezone for price calculations
            token: Tibber API access token
            min_time_between_API_calls: Refresh interval in seconds (default from constants)
            delay_evaluation_by_seconds: Maximum random delay
            **kwargs: Additional arguments passed to BaseFetcher
        """
        # Initialize token first (needed for get_provider_id)
        if not token:
            raise ValueError("[Tibber] Access token is required")
        
        self.access_token = token
        self.url = "https://api.tibber.com/v1-beta/gql"
        
        # GraphQL query for price data
        self.query_data = """{
            "query": "{viewer {homes {currentSubscription {priceInfo(resolution: HOURLY) { current {total startsAt } today {total startsAt } tomorrow {total startsAt }}}}}}"
        }"""
        
        # Now call super().__init__ (which calls get_provider_id)
        super().__init__(
            timezone=timezone,
            min_time_between_API_calls=min_time_between_API_calls,
            delay_evaluation_by_seconds=delay_evaluation_by_seconds,
            **kwargs
        )

    def get_provider_id(self) -> str:
        """Return unique identifier for this provider."""
        # Use token hash for uniqueness without exposing the actual token
        token_hash = hash(self.access_token) % 10000
        return f"tibber_{token_hash}"

    def get_raw_data_from_provider(self) -> dict:
        """
        Fetch raw data from the Tibber API using unified HTTP client.
        
        Returns:
            Raw JSON data from Tibber GraphQL API
            
        Raises:
            ConnectionError: If the API request fails
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Use the unified HTTP client with automatic rate limiting and timeouts
            response = self.http_client.post_with_rate_limit_handling(
                url=self.url,
                data=self.query_data,
                headers=headers,
                provider_id=self.get_provider_id(),
                provider_type=self.provider_type,
                max_delay=self.max_delay,
                last_update=self.last_update,
                timeout=30  # External API timeout
            )
            
            return response.json()
            
        except Exception as e:
            raise ConnectionError(f'[Tibber] API request failed: {e}') from e

    def get_prices_from_raw_data(self) -> Dict[int, float]:
        """
        Process raw Tibber data into standardized price format.
        
        Returns:
            Dict mapping hour offsets (0, 1, 2, ...) to prices in EUR/kWh
            
        Raises:
            ValueError: If raw data format is invalid
        """
        try:
            homeid = 0  # Use first home (most common case)
            rawdata = self.raw_data['data']
            now = datetime.datetime.now().astimezone(self.timezone)
            prices = {}
            
            # Process both today and tomorrow prices
            price_info = rawdata['viewer']['homes'][homeid]['currentSubscription']['priceInfo']
            
            for day in ['today', 'tomorrow']:
                if day not in price_info:
                    continue
                    
                dayinfo = price_info[day]
                for item in dayinfo:
                    # Parse ISO format timestamp
                    timestamp = datetime.datetime.fromisoformat(item['startsAt'])
                    
                    # Calculate hour offset from now
                    diff = timestamp - now
                    rel_hour = math.ceil(diff.total_seconds() / 3600)
                    
                    # Only include future hours
                    if rel_hour >= 0:
                        prices[rel_hour] = item['total']
            
            return prices
            
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f'[Tibber] Invalid raw data format: {e}') from e

    def get_recommended_refresh_interval(self) -> int:
        """
        Get recommended refresh interval for Tibber data.
        
        Tibber updates prices daily around 13:00 CET for next day,
        but we check every 30 minutes for responsive updates.
        
        Returns:
            Recommended refresh interval in seconds (1800s = 30 min)
        """
        return self.refresh_interval  # 30 minutes for external API