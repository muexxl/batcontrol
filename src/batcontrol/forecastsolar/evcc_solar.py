"""
Refactored EvccSolar using BaseFetcher infrastructure.

This version consolidates the caching, delay, and error handling logic
into the shared BaseFetcher class.
"""
import datetime
import math
import logging

from ..fetching import BaseFetcher, PROVIDER_TYPE_LOCAL
from ..fetching.constants import LOCAL_REFRESH_INTERVAL
from .forecastsolar_interface import ForecastSolarInterface

logger = logging.getLogger(__name__)


class EvccSolar(BaseFetcher, ForecastSolarInterface):
    """
    Refactored evcc API to get solar forecast data.

    Now inherits from both ForecastSolarInterface and BaseFetcher
    to use shared infrastructure.
    """

    # pylint: disable=too-many-arguments,too-many-positional-arguments,unused-argument
    def __init__(self, pvinstallations, timezone, api_delay,
                 cache_manager=None, http_client=None, rate_limit_manager=None):
        """
        Initialize the EvccSolar instance.

        Args:
            pvinstallations (list): List of installation configurations. For evcc-solar,
                                  this should contain a single entry with 'url' key.
            timezone: Timezone information for the forecast data
            api_delay (int): Delay in seconds for API evaluation
            cache_manager: Shared cache manager (deprecated, use BaseFetcher)
            http_client: Shared HTTP client (deprecated, use BaseFetcher)
            rate_limit_manager: Shared rate limit manager (deprecated, use BaseFetcher)
        """
        # Initialize BaseFetcher with local provider settings for 15min refresh
        BaseFetcher.__init__(
            self,
            timezone=timezone,
            provider_type=PROVIDER_TYPE_LOCAL,
            refresh_interval=LOCAL_REFRESH_INTERVAL,  # Use constant (15 min)
            max_delay=api_delay,
            shared_cache_manager=cache_manager,
            shared_http_client=http_client
        )

        self.pvinstallations = pvinstallations

        # Extract URL from pvinstallations config
        if not pvinstallations or not isinstance(pvinstallations, list):
            raise ValueError("[EvccSolar] pvinstallations must be a non-empty list")

        if len(pvinstallations) != 1:
            raise ValueError(
                "[EvccSolar] evcc-solar provider expects exactly one "
                "installation configuration"
            )

        installation = pvinstallations[0]
        if 'url' not in installation:
            raise ValueError("[EvccSolar] URL must be provided in installation configuration")

        self.url = installation['url']
        logger.info(
            '[EvccSolar] Initialized with URL: %s (refresh_interval: %ss, cache_ttl: %ss)',
            self.url, self.refresh_interval, self.cache_ttl
        )

    def get_provider_id(self) -> str:
        """Return unique identifier for this provider."""
        return "evcc_solar"

    def get_forecast(self) -> dict[int, float]:
        """
        Get solar forecast data from evcc API.

        Returns:
            dict[int, float]: Dictionary with relative hours as keys and solar production
                            values (in Watts) as values
        """
        return self.get_data()

    def get_raw_data_from_provider(self) -> dict:
        """
        Fetch raw data from the evcc API.

        Returns:
            Raw JSON data from evcc API
        """
        response = self.http_client.get_with_rate_limit_handling(
            url=self.url,
            provider_id=self.get_provider_id(),
            provider_type=self.provider_type,
            max_delay=self.max_delay,
            last_update=self.last_update
        )

        raw_data = response.json()
        logger.debug(
            '[EvccSolar] Received raw data with %d entries',
            len(raw_data.get('result', {}).get('rates', []))
        )
        return raw_data

    # pylint: disable=too-many-locals
    def process_raw_data(self, raw_data: dict) -> dict[int, float]:
        """
        Process the raw data from the evcc API and return a dictionary of forecast values
        indexed by relative hour.

        Args:
            raw_data: Raw JSON data from evcc API

        Returns:
            dict[int, float]: Hourly forecast data
        """
        # Initialize dictionaries for accumulating values and counting intervals per hour
        hourly_values = {}
        hourly_counts = {}

        # Return empty prediction if no data available
        if not raw_data:
            logger.warning('[EvccSolar] No results from evcc Solar API available')
            raise RuntimeWarning('No results from evcc Solar API available')

        # Calculate current hour for relative hour calculation
        # Use now(tz=) to ensure consistent timezone handling in CI environments
        now = datetime.datetime.now(tz=self.timezone)
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        # Process rates from evcc API
        rates = raw_data.get('result', {}).get('rates', [])

        for rate in rates:
            try:
                # Parse start time of this interval
                start_time_str = rate.get('start')
                if not start_time_str:
                    continue

                start_time = datetime.datetime.fromisoformat(start_time_str)

                # Calculate relative hour from current hour
                time_diff = start_time - current_hour
                relative_hour = math.ceil(time_diff.total_seconds() / 3600) - 1

                # Only include future hours (relative_hour >= 0)
                if relative_hour >= 0:
                    # Get power value, treating None as 0
                    price_raw = rate.get('price', 0)
                    power_value = float(price_raw) if price_raw is not None else 0.0

                    # Accumulate values for this hour
                    if relative_hour in hourly_values:
                        hourly_values[relative_hour] += power_value
                        hourly_counts[relative_hour] += 1
                    else:
                        hourly_values[relative_hour] = power_value
                        hourly_counts[relative_hour] = 1

            except (ValueError, TypeError, KeyError) as e:
                logger.warning('[EvccSolar] Error processing rate entry: %s', e)
                continue

        # Calculate average power for each hour and convert to final forecast
        forecast = {}
        for hour, value in hourly_values.items():
            # Calculate average power for this hour
            avg_power = value / hourly_counts[hour]
            # Round to 1 decimal place for consistency
            forecast[hour] = round(avg_power, 1)

        # Fill in missing hours with 0 values up to the maximum hour
        if forecast:
            max_hour = max(forecast.keys())
            for h in range(max_hour + 1):
                if h not in forecast:
                    forecast[h] = 0.0

        # Sort the output by hour
        forecast = dict(sorted(forecast.items()))

        logger.info('[EvccSolar] Processed forecast for %d hours', len(forecast))
        return forecast

    def get_recommended_refresh_interval(self) -> int:
        """
        Get recommended refresh interval for EVCC solar provider.

        Local EVCC APIs can be refreshed less frequently than external APIs.
        """
        return 3600  # 1 hour for local APIs


# EvccSolar ist jetzt die Standard-Implementierung (vorher refactored)
