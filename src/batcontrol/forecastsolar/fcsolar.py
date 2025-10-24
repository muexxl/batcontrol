""" Refactored FCSolar module using BaseFetcher architecture

See https://forecast.solar/ for more information

Refactored to use:
- BaseFetcher for shared infrastructure
- Async HTTP client with connection pooling
- Shared cache manager
- Unified rate limiting
- Thread-safe operations
"""

import datetime
import logging
from ..fetching import BaseFetcher, PROVIDER_TYPE_EXTERNAL
from ..fetching.constants import EXTERNAL_REFRESH_INTERVAL
from .forecastsolar_interface import ForecastSolarInterface

logger = logging.getLogger(__name__)
logger.info('Loading module')


class FCSolar(BaseFetcher, ForecastSolarInterface):
    """
    Refactored FCSolar provider using modern BaseFetcher architecture.

    Features:
    - Shared cache manager for improved performance
    - HTTP client with connection pooling
    - Unified rate limiting across all providers
    - Thread-safe operations
    - Automatic retry handling
    """

    def __init__(self, pvinstallations, timezone, delay_evaluation_by_seconds, *,
                 cache_manager=None, http_client=None, rate_limit_manager=None):
        """
        Initialize FCSolar provider with shared infrastructure.

        Args:
            pvinstallations: PV installation configurations
            timezone: Timezone for the installation
            delay_evaluation_by_seconds: Random delay for API calls
            cache_manager: Shared cache manager instance
            http_client: Shared HTTP client instance
            rate_limit_manager: Shared rate limit manager instance
        """
        # Initialize BaseFetcher with external provider settings for 30min refresh
        BaseFetcher.__init__(
            self,
            timezone=timezone,
            provider_type=PROVIDER_TYPE_EXTERNAL,
            refresh_interval=EXTERNAL_REFRESH_INTERVAL,  # Use constant (30 min)
            max_delay=delay_evaluation_by_seconds,
            shared_cache_manager=cache_manager,
            shared_http_client=http_client
        )

        # Store rate limit manager reference for provider info
        self.rate_limit_manager = rate_limit_manager

        # Convert list format to dict format if needed
        if isinstance(pvinstallations, list):
            # Convert from list of dicts to dict keyed by 'name'
            # Keep all the other fields in the dict
            self.pvinstallations = {
                install.pop('name'): install for install in 
                [dict(inst) for inst in pvinstallations]  # Create copies to avoid modifying originals
            }
        else:
            self.pvinstallations = pvinstallations
        self.results = {}

        self.base_url = "https://api.forecast.solar"

        # Legacy compatibility
        self.seconds_between_updates = self.refresh_interval

        logger.debug("FCSolar pvinstallations: %s", self.pvinstallations)
        logger.info("FCSolar provider initialized with shared infrastructure "
                   "(refresh_interval: %ss, cache_ttl: %ss)",
                   self.refresh_interval, self.cache_ttl)

    def get_provider_id(self) -> str:
        """Return unique identifier for this provider."""
        return "fcsolar"

    def get_forecast(self) -> dict:
        """
        Get hourly forecast from Forecast.Solar API.

        Returns:
            dict: Hourly forecast data for next 48 hours

        Raises:
            RuntimeWarning: If no forecast data is available
        """
        return self.get_data()

    def get_raw_data_from_provider(self) -> dict:
        """
        Fetch raw data from the Forecast.Solar API.

        Returns:
            Raw JSON data from all installations
        """
        logger.debug("Fetching raw forecast data from Forecast.Solar API")

        raw_results = {}
        for name, unit in self.pvinstallations.items():
            try:
                raw_results[name] = self._fetch_installation_data(name, unit)
            except Exception as exc:
                logger.error("Failed to fetch data for installation %s: %s", name, exc)
                # Continue with other installations

        return raw_results

    def process_raw_data(self, raw_data: dict) -> dict:
        """
        Process raw Forecast.Solar data into hourly forecast format.

        Args:
            raw_data: Raw data from all installations

        Returns:
            dict: Hourly forecast with hour offsets as keys
        """
        self.results = raw_data

        # Return empty prediction if no results available
        if not self.results:
            logger.warning('No results from Forecast.Solar API available')
            raise RuntimeWarning('No results from Forecast.Solar API available')

        # Process results into hourly prediction
        prediction = {}
        now = datetime.datetime.now().astimezone(self.timezone)
        current_hour = datetime.datetime(
            now.year, now.month, now.day, now.hour).astimezone(self.timezone)

        # Get response timezone from first result
        result = next(iter(self.results.values()))
        response_time_string = result['message']['info']['time']
        response_time = datetime.datetime.fromisoformat(response_time_string)
        response_timezone = response_time.tzinfo

        for _, result in self.results.items():
            for isotime, value in result['result'].items():
                timestamp = datetime.datetime.fromisoformat(
                    isotime).astimezone(response_timezone)

                if timestamp < current_hour:
                    continue

                diff = timestamp - current_hour
                rel_hour = int(diff.total_seconds() / 3600)

                if 0 <= rel_hour <= 48:
                    if rel_hour in prediction:
                        prediction[rel_hour] += value
                    else:
                        prediction[rel_hour] = value

        # Fill missing hours with 0
        for hour in range(49):
            if hour not in prediction:
                prediction[hour] = 0

        return prediction

    def _fetch_installation_data(self, name: str, unit: dict) -> dict:
        """
        Fetch forecast data for a single PV installation.

        Args:
            name: Installation name
            unit: Installation configuration

        Returns:
            dict: Raw API response data
        """
        # Build API URL
        url = self._build_api_url(name, unit)

        logger.info('Requesting information for PV installation %s', name)

        # Use shared HTTP client for request with full rate limiting
        response = self.http_client.get_with_rate_limit_handling(
            url,
            provider_id=self.get_provider_id(),
            provider_type=self.provider_type,
            max_delay=self.max_delay,
            last_update=self.last_update,
            timeout=30
        )

        if response.status_code == 200:
            response_data = response.json()
            logger.debug("Successfully fetched data for %s", name)
            return response_data

        if response.status_code == 429:
            # Rate limit is already handled by HTTP client
            logger.warning('Rate limit exceeded (429) - handled by HTTP client')
            raise RuntimeError('API rate limit exceeded')

        logger.warning('Forecast.Solar API returned %s - %s',
                        response.status_code, response.text)
        raise RuntimeError(f'API request failed with status {response.status_code}')

    def _build_api_url(self, name: str, unit: dict) -> str:
        """
        Build API URL for a PV installation.

        Args:
            name: Installation name
            unit: Installation configuration

        Returns:
            str: Complete API URL
        """
        # Extract required parameters
        lat = unit.get('lat')
        lon = unit.get('lon')
        dec = unit.get('declination', unit.get('dec'))
        az = unit.get('azimuth', unit.get('az'))
        kwp = unit.get('kWp', unit.get('kwp'))

        # Validate required parameters
        logger.debug("Building URL for %s: lat=%s, lon=%s, dec=%s, az=%s, kwp=%s, unit=%s", 
                    name, lat, lon, dec, az, kwp, unit)
        if not all([lat is not None, lon is not None, dec is not None, az is not None, kwp is not None]):
            raise ValueError(f"Missing required parameters for installation {name}")

        # Handle optional API key
        apikey = unit.get('apikey', '')
        apikey_urlmod = f"{apikey}/" if apikey else ""

        # Handle optional horizon parameter
        horizon_querymod = ""
        if 'horizon' in unit and unit['horizon'] is not None:
            horizon_querymod = f"?horizon={unit['horizon']}"

        # Build complete URL
        url = (f"{self.base_url}/{apikey_urlmod}estimate/"
               f"watthours/period/{lat}/{lon}/{dec}/{az}/{kwp}"
               f"{horizon_querymod}")

        return url

    def _build_cache_key(self, provider: str, name: str, unit: dict) -> str:
        """
        Build cache key for installation data.

        Args:
            provider: Provider name
            name: Installation name
            unit: Installation configuration

        Returns:
            str: Cache key
        """
        # Include key parameters in cache key
        key_params = [
            unit.get('lat', ''),
            unit.get('lon', ''),
            unit.get('declination', unit.get('dec', '')),
            unit.get('azimuth', unit.get('az', '')),
            unit.get('kWp', unit.get('kwp', '')),
            unit.get('horizon', '')
        ]

        return f"{provider}:{name}:{'_'.join(map(str, key_params))}"

    def get_provider_info(self) -> dict:
        """Get provider information for monitoring."""
        is_rate_limited = (self.rate_limit_manager.is_rate_limited(self.get_provider_id())
                          if self.rate_limit_manager else False)
        return {
            'name': 'FCSolar',
            'type': 'solar_forecast',
            'url': self.base_url,
            'installations': len(self.pvinstallations),
            'last_update': self.last_update,
            'refresh_interval': self.refresh_interval,
            'cache_ttl': self.cache_ttl,
            'rate_limited': is_rate_limited
        }
