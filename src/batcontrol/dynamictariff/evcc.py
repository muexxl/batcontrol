"""
Refactored EVCC Class using unified fetching infrastructure.

This module implements the EVCC API to retrieve dynamic electricity prices.
It inherits from the refactored DynamicTariffBaseclass.

Classes:
    EvccRefactored: A class to interact with the EVCC API using BaseFetcher infrastructure.

Methods:
    __init__(self, timezone, url: str, min_time_between_API_calls=3600):
        Initializes the EvccRefactored class with the specified parameters.

    get_raw_data_from_provider(self):
        Fetches raw data from the EVCC API using unified HTTP client.

    get_prices_from_raw_data(self):
        Processes the raw data to extract electricity prices with hourly averaging.
"""
import datetime
from typing import Dict
from urllib.parse import urlparse

from .baseclass import DynamicTariffBaseclass
from ..fetching.constants import PROVIDER_TYPE_LOCAL, LOCAL_REFRESH_INTERVAL


class Evcc(DynamicTariffBaseclass):
    """
    Refactored EVCC API implementation using unified fetching infrastructure.

    Inherits from DynamicTariffBaseclass (which extends BaseFetcher) to eliminate
    duplicated caching, delay, and error handling logic.

    EVCC is a local API, so it uses local timeouts and longer cache duration.
    """

    def __init__(
        self,
        timezone,
        url: str,
        min_time_between_API_calls: int = LOCAL_REFRESH_INTERVAL,  # Use constant (15 min)
        delay_evaluation_by_seconds: int = 0,  # No delay for local API
        **kwargs
    ):
        """
        Initialize EVCC provider.

        Args:
            timezone: Timezone for price calculations
            url: EVCC API endpoint URL
            min_time_between_API_calls: Refresh interval in seconds (default from constants)
            delay_evaluation_by_seconds: Maximum random delay (0 for local API)
            **kwargs: Additional arguments passed to BaseFetcher
        """
        # Initialize URL first (needed for get_provider_id)
        if not url:
            raise ValueError("[EVCC] API URL is required")

        self.url = url

        # Now call super().__init__ (which calls get_provider_id)
        super().__init__(
            timezone=timezone,
            min_time_between_API_calls=min_time_between_API_calls,
            delay_evaluation_by_seconds=delay_evaluation_by_seconds,
            **kwargs
        )

        # Override provider type to LOCAL for proper timeout and refresh handling
        self.provider_type = PROVIDER_TYPE_LOCAL

    def get_provider_id(self) -> str:
        """Return unique identifier for this provider."""
        # Use URL host for uniqueness
        try:
            parsed = urlparse(self.url)
            host = parsed.netloc or "localhost"
            return f"evcc_{host}"
        except Exception:  # pylint: disable=broad-exception-caught
            return "evcc_unknown"

    def get_raw_data_from_provider(self) -> dict:
        """
        Fetch raw data from the EVCC API using unified HTTP client.

        Returns:
            Raw JSON data from EVCC API

        Raises:
            ConnectionError: If the API request fails
        """
        try:
            # Use the unified HTTP client with local API timeout (10s)
            response = self.http_client.get_with_rate_limit_handling(
                url=self.url,
                provider_id=self.get_provider_id(),
                provider_type=self.provider_type,
                max_delay=self.max_delay,
                last_update=self.last_update,
                timeout=10  # Local API timeout
            )

            return response.json()

        except Exception as e:
            raise ConnectionError(f'[EVCC] API request failed: {e}') from e

    def get_prices_from_raw_data(self) -> Dict[int, float]:
        """
        Process raw EVCC data into standardized price format.

        Handles both the legacy format (rates in 'result' field) and the
        newer format (rates directly in response). Also handles sub-hourly
        intervals by averaging prices within each hour.

        Returns:
            Dict mapping hour offsets (0, 1, 2, ...) to prices in EUR/kWh

        Raises:
            ValueError: If raw data format is invalid
        """
        try:
            # Handle both legacy and new EVCC response formats
            data = self.raw_data.get('rates', None)
            if data is None:
                # Prior to evcc 0.207.0 the rates were in the 'result' field
                data = self.raw_data['result']['rates']

            now = datetime.datetime.now().astimezone(self.timezone)
            # Get the start of the current hour
            current_hour_start = now.replace(minute=0, second=0, microsecond=0)

            # Use a dictionary to collect all prices for each hour
            hourly_prices = {}

            for item in data:
                # Parse ISO format timestamp
                timestamp = datetime.datetime.fromisoformat(item['start']).astimezone(self.timezone)

                # Get the start of the hour for this timestamp
                interval_hour_start = timestamp.replace(minute=0, second=0, microsecond=0)

                # Calculate relative hour based on hour boundaries
                diff = interval_hour_start - current_hour_start
                rel_hour = int(diff.total_seconds() / 3600)

                # Only include future hours
                if rel_hour >= 0:
                    # Handle both old and new EVCC field names
                    if item.get('value', None) is not None:
                        price = item['value']  # Since evcc 0.203.0
                    else:
                        price = item['price']  # Legacy format

                    # Collect all prices for this hour (for sub-hourly averaging)
                    if rel_hour not in hourly_prices:
                        hourly_prices[rel_hour] = []
                    hourly_prices[rel_hour].append(price)

            # Calculate average for each hour (handles sub-hourly intervals)
            prices = {}
            for hour, price_list in hourly_prices.items():
                prices[hour] = sum(price_list) / len(price_list)

            return prices

        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f'[EVCC] Invalid raw data format: {e}') from e

    def get_recommended_refresh_interval(self) -> int:
        """
        Get recommended refresh interval for EVCC data.

        EVCC is a local API that caches external tariff data,
        so 15-minute refresh interval is appropriate for local responsiveness.

        Returns:
            Recommended refresh interval in seconds (900s = 15 min)
        """
        return self.refresh_interval  # 15 minutes for local API
