"""
Refactored Awattar Class using unified fetching infrastructure.

This module implements the Awattar API to retrieve dynamic electricity prices.
It inherits from the refactored DynamicTariffBaseclass.

Classes:
    AwattarRefactored: A class to interact with the Awattar API using BaseFetcher infrastructure.

Methods:
    __init__(self, timezone, country: str, min_time_between_API_calls=900,
             delay_evaluation_by_seconds=0):
        Initializes the AwattarRefactored class with the specified parameters.

    get_raw_data_from_provider(self):
        Fetches raw data from the Awattar API using unified HTTP client.

    get_prices_from_raw_data(self):
        Processes the raw data to extract and calculate electricity prices.
"""
import datetime
import math
from typing import Dict

from .baseclass import DynamicTariffBaseclass
from ..fetching.constants import EXTERNAL_REFRESH_INTERVAL


class Awattar(DynamicTariffBaseclass):
    """
    Refactored Awattar API implementation using unified fetching infrastructure.

    Inherits from DynamicTariffBaseclass (which extends BaseFetcher) to eliminate
    duplicated caching, delay, and error handling logic.
    """

    def __init__(
        self,
        timezone,
        country: str,
        min_time_between_API_calls: int = EXTERNAL_REFRESH_INTERVAL,  # Use constant (30 min)
        delay_evaluation_by_seconds: int = 30,  # Max 30s random delay
        **kwargs
    ):
        """
        Initialize Awattar provider.

        Args:
            timezone: Timezone for price calculations
            country: Country code ('at' or 'de')
            min_time_between_API_calls: Refresh interval in seconds (default from constants)
            delay_evaluation_by_seconds: Maximum random delay
            **kwargs: Additional arguments passed to BaseFetcher
        """
        # Initialize country first (needed for get_provider_id)
        country = country.lower()
        if country in ['at', 'de']:
            self.country = country  # Store country for provider_id
            self.url = f'https://api.awattar.{country}/v1/marketdata'
        else:
            raise ValueError(f'[Awattar] Country Code {country} not supported')

        # Now call super().__init__ (which calls get_provider_id)
        super().__init__(
            timezone=timezone,
            min_time_between_API_calls=min_time_between_API_calls,
            delay_evaluation_by_seconds=delay_evaluation_by_seconds,
            **kwargs
        )

        # Price calculation parameters
        self.vat = 0.0
        self.price_fees = 0.0
        self.price_markup = 0.0

    def get_provider_id(self) -> str:
        """Return unique identifier for this provider."""
        return f"awattar_{self.country}"

    def set_price_parameters(self, vat: float, price_fees: float, price_markup: float):
        """
        Set the extra price parameters for the tariff calculation.

        Args:
            vat: VAT rate (e.g., 0.20 for 20%)
            price_fees: Fixed fees per kWh
            price_markup: Markup percentage (e.g., 0.10 for 10%)
        """
        self.vat = vat
        self.price_fees = price_fees
        self.price_markup = price_markup

    def get_raw_data_from_provider(self) -> dict:
        """
        Fetch raw data from the Awattar API using unified HTTP client.

        Returns:
            Raw JSON data from Awattar API

        Raises:
            ConnectionError: If the API request fails
        """
        try:
            # Use the unified HTTP client with automatic rate limiting and timeouts
            response = self.http_client.get_with_rate_limit_handling(
                url=self.url,
                provider_id=self.get_provider_id(),
                provider_type=self.provider_type,
                max_delay=self.max_delay,
                last_update=self.last_update,
                timeout=30  # External API timeout
            )

            return response.json()

        except Exception as e:
            raise ConnectionError(f'[Awattar] API request failed: {e}') from e

    def get_prices_from_raw_data(self) -> Dict[int, float]:
        """
        Process raw Awattar data into standardized price format.

        Returns:
            Dict mapping hour offsets (0, 1, 2, ...) to prices in EUR/kWh

        Raises:
            ValueError: If raw data format is invalid
        """
        try:
            data = self.raw_data['data']
            now = datetime.datetime.now().astimezone(self.timezone)
            prices = {}

            for item in data:
                # Convert timestamp from milliseconds to datetime
                timestamp = datetime.datetime.fromtimestamp(
                    item['start_timestamp'] / 1000
                ).astimezone(self.timezone)

                # Calculate hour offset from now
                diff = timestamp - now
                rel_hour = math.ceil(diff.total_seconds() / 3600)

                # Only include future hours
                if rel_hour >= 0:
                    # Calculate final price with markup, fees, and VAT
                    end_price = (
                        item['marketprice'] / 1000 * (1 + self.price_markup) + self.price_fees
                    ) * (1 + self.vat)

                    prices[rel_hour] = end_price

            return prices

        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f'[Awattar] Invalid raw data format: {e}') from e

    def get_recommended_refresh_interval(self) -> int:
        """
        Get recommended refresh interval for Awattar data.
        Awattar updates prices once a day around 14:00 CET, but we check
        every 30 minutes for responsive updates and potential corrections.

        Returns:
            Recommended refresh interval in seconds (1800s = 30 min)
        """
        return self.refresh_interval  # 30 minutes for external API
