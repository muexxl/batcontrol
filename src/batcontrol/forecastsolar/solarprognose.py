""" Refactored SolarPrognose module using BaseFetcher architecture

https://www.solarprognose.de/web/de/solarprediction/page/api

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

# SolarPrognose API Status Codes
STATUS_OK = 0
STATUS_ERROR_INVALID_ACCESS_TOKEN = -2
STATUS_ERROR_MISSING_PARAMETER_ACCESS_TOKEN = -3
STATUS_ERROR_EMPTY_PARAMETER_ACCESS_TOKEN = -4
STATUS_ERROR_INVALID_TYPE = -5
STATUS_ERROR_MISSING_TYPE = -6
STATUS_ERROR_INVALID_ID = -7
STATUS_ERROR_ACCESS_DENIED = -8
STATUS_ERROR_INVALID_ITEM = -9
STATUS_ERROR_INVALID_TOKEN = -10
STATUS_ERROR_NO_SOLAR_DATA_AVAILABLE = -11
STATUS_ERROR_NO_DATA = -12
STATUS_ERROR_INTERNAL_ERROR = -13
STATUS_ERROR_UNKNOWN_ERROR = -14
STATUS_ERROR_INVALID_START_DAY = -15
STATUS_ERROR_INVALID_END_DAY = -16
STATUS_ERROR_INVALID_DAY = -17
STATUS_ERROR_INVALID_WEATHER_SERVICE_ID = -18
STATUS_ERROR_DAILY_QUOTA_EXCEEDED = -19
STATUS_ERROR_INVALID_OR_MISSING_ELEMENT_ITEM = -20
STATUS_ERROR_NO_PARAMETER = -21
STATUS_ERROR_INVALID_PERIOD = -22
STATUS_ERROR_INVALID_START_EPOCH_TIME = -23
STATUS_ERROR_INVALID_END_EPOCH_TIME = -24
STATUS_ERROR_ACCESS_DENIED_TO_ITEM_DUE_TO_LIMIT = -25
STATUS_ERROR_NO_CLEARSKY_VALUES = -26
STATUS_ERROR_MISSING_INPUT_ID_AND_TOKEN = -27
STATUS_ERROR_INVALID_ALGORITHM = -28
STATUS_ERROR_FAILED_TO_LOAD_WEATHER_LOCATION_ITEM = -29


class SolarPrognose(BaseFetcher, ForecastSolarInterface):
    """
    Refactored SolarPrognose provider using modern BaseFetcher architecture.

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
        Initialize SolarPrognose provider with shared infrastructure.

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

        self.base_url = "https://www.solarprognose.de/web/solarprediction/api/v1"

        # Legacy compatibility
        self.seconds_between_updates = self.refresh_interval

        logger.info("SolarPrognose provider initialized with shared infrastructure "
                   "(refresh_interval: %ss, cache_ttl: %ss)",
                   self.refresh_interval, self.cache_ttl)

    def get_provider_id(self) -> str:
        """Return unique identifier for this provider."""
        return "solarprognose"

    def get_forecast(self) -> dict:
        """
        Get hourly forecast from SolarPrognose API.

        Returns:
            dict: Hourly forecast data for next 48 hours

        Raises:
            RuntimeWarning: If no forecast data is available
        """
        return self.get_data()

    def get_raw_data_from_provider(self) -> dict:
        """
        Fetch raw data from the SolarPrognose API.

        Returns:
            Raw JSON data from all installations
        """
        logger.debug("Fetching raw forecast data from SolarPrognose API")

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
        Process raw SolarPrognose data into hourly forecast format.

        Args:
            raw_data: Raw data from all installations

        Returns:
            dict: Hourly forecast with hour offsets as keys
        """
        self.results = raw_data

        # Return empty prediction if no results available
        if not self.results:
            logger.warning('No results from SolarPrognose API available')
            raise RuntimeWarning('No results from SolarPrognose API available')

        # Process results into hourly prediction
        prediction = {}
        now = datetime.datetime.now().astimezone(self.timezone)
        now_ts = now.timestamp()

        for _, result in self.results.items():
            for key in result['data']:
                timestamp = int(key)
                value = result['data'][key][0]

                if int(timestamp) < now_ts:
                    continue

                diff = timestamp - now_ts
                rel_hour = int(diff / 3600)

                if rel_hour >= 0:
                    # API delivers values in kW, we need W
                    if rel_hour in prediction:
                        prediction[rel_hour] += value * 1000
                    else:
                        prediction[rel_hour] = value * 1000

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
            status_code = response_data.get('status')

            if status_code == STATUS_OK:
                # Success
                logger.debug("Successfully fetched data for %s", name)
                return response_data

            if status_code in [STATUS_ERROR_DAILY_QUOTA_EXCEEDED,
                              STATUS_ERROR_ACCESS_DENIED_TO_ITEM_DUE_TO_LIMIT]:
                logger.error('Limit exceeded for installation %s - status: %s',
                            name, status_code)
                # Parse retry-after info and set in RateLimitManager
                self._handle_api_retry_after(response_data)
                raise RuntimeError(f'API quota exceeded for {name}')

            logger.error('API returned status code %s', status_code)
            raise RuntimeError(f'API returned status code {status_code}')

        if response.status_code == 401:
            logger.error('API returned 401 - Unauthorized, check API key')
            raise RuntimeError('API returned 401 - Unauthorized')

        if response.status_code == 429:
            # Rate limit handled by HTTP client, but parse additional info
            logger.warning('Rate limit exceeded (429)')
            self._handle_api_retry_after(response.json() if response.content else {})
            raise RuntimeError('API rate limit exceeded')

        logger.warning('SolarPrognose API returned %s - %s',
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
        apikey = unit.get('apikey')
        if not apikey:
            raise ValueError(f"No API key provided for installation {name}")

        algorithm = unit.get('algorithm', 'mosmix_dmi')

        # Build query parameters
        params = {
            'access-token': apikey,
            'algorithm': algorithm,
            'type': 'hourly',
            '_format': 'json'
        }

        # Add optional project parameter
        if unit.get('project'):
            params['project'] = name

        # Build item query for PV parameters
        item_parts = []
        for param in ['lat', 'lon', 'dec', 'az', 'kwp']:
            if param in unit:
                item_parts.append(f'{param}:{unit[param]}')

        if item_parts:
            params['item'] = f"&item={'|'.join(item_parts)}"

        # Build URL with parameters
        url = self.base_url + '?'
        url += '&'.join(f'{k}={v}' for k, v in params.items())

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
            unit.get('kwp', ''),
            unit.get('algorithm', 'mosmix_dmi')
        ]

        return f"{provider}:{name}:{'_'.join(map(str, key_params))}"

    def _handle_api_retry_after(self, response_data: dict) -> None:
        """
        Handle retry-after information from API response.

        Args:
            response_data: API response data
        """
        retry_after_timestamp = 0

        if 'preferredNextApiRequestAt' in response_data:
            if 'epochTimeUtc' in response_data['preferredNextApiRequestAt']:
                retry_after_timestamp = (
                    response_data['preferredNextApiRequestAt']['epochTimeUtc'])

        if retry_after_timestamp > 0 and self.rate_limit_manager:
            retry_at_time = datetime.datetime.fromtimestamp(
                retry_after_timestamp, tz=datetime.timezone.utc)

            # Create a mock response with X-Ratelimit-Retry-At header
            class MockResponse:  # pylint: disable=too-few-public-methods
                """Mock response for rate limit manager."""
                def __init__(self):
                    self.headers = {'X-Ratelimit-Retry-At': retry_at_time.isoformat()}
                    self.status_code = 429

            # Use the centralized rate limit manager
            self.rate_limit_manager.set_rate_limit_from_response(
                self.get_provider_id(),
                MockResponse()
            )

            logger.debug("Rate limit window set until timestamp %s via RateLimitManager",
                        retry_after_timestamp)
        else:
            logger.warning("Rate limit exceeded but no retry-after information available")

    def get_provider_info(self) -> dict:
        """Get provider information for monitoring."""
        is_rate_limited = (self.rate_limit_manager.is_rate_limited(self.get_provider_id())
                          if self.rate_limit_manager else False)
        return {
            'name': 'SolarPrognose',
            'type': 'solar_forecast',
            'url': self.base_url,
            'installations': len(self.pvinstallations),
            'last_update': self.last_update,
            'refresh_interval': self.refresh_interval,
            'cache_ttl': self.cache_ttl,
            'rate_limited': is_rate_limited
        }
