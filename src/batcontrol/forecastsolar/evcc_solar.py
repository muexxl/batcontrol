"""
This module defines the EvccSolar class, which is used to interact with the evcc API to fetch
solar forecast data.

Classes:
    EvccSolar: A class to interact with the evcc API and process solar forecast data.

Methods:
    __init__(self, pvinstallations, timezone, api_delay):
        Initializes the EvccSolar instance with the given timezone and configuration.

    get_forecast(self):
        Fetches solar forecast data from the evcc API and returns it as a dictionary.

Configuration:
    To use evcc-solar as your solar forecast provider, configure your batcontrol_config.yaml 
    as follows:

    solar_forecast_provider: evcc-solar
    pvinstallations:
      - url: https://your-evcc-instance.local/api/tariff/solar

    The URL should point to your evcc instance's solar tariff API endpoint.

Usage:
    To use this module, instantiate the EvccSolar class with appropriate configuration
    and call get_forecast() to retrieve solar production forecasts.
"""
import datetime
import math
import time
import random
import logging
import requests
from .forecastsolar_interface import ForecastSolarInterface

logger = logging.getLogger(__name__)

class EvccSolar(ForecastSolarInterface):
    """ Implement evcc API to get solar forecast data
        Inherits from ForecastSolarInterface
    """
    def __init__(self, pvinstallations, timezone, api_delay):
        """
        Initialize the EvccSolar instance.

        Args:
            pvinstallations (list): List of installation configurations. For evcc-solar,
                                  this should contain a single entry with 'url' key.
            timezone: Timezone information for the forecast data
            api_delay (int): Delay in seconds for API evaluation
        """
        self.pvinstallations = pvinstallations
        self.timezone = timezone
        self.api_delay = api_delay
        self.raw_data = {}
        self.last_update = 0
        self.min_time_between_updates = 900  # 15 minutes default

        # Extract URL from pvinstallations config
        if not pvinstallations or not isinstance(pvinstallations, list):
            raise ValueError("[EvccSolar] pvinstallations must be a non-empty list")

        if len(pvinstallations) != 1:
            raise ValueError("[EvccSolar] evcc-solar provider expects exactly one installation configuration")

        installation = pvinstallations[0]
        if 'url' not in installation:
            raise ValueError("[EvccSolar] URL must be provided in installation configuration")

        self.url = installation['url']
        logger.info('Initialized EvccSolar with URL: %s', self.url)

    def get_forecast(self) -> dict[int, float]:
        """
        Get solar forecast data from evcc API.

        Returns:
            dict[int, float]: Dictionary with relative hours as keys and solar production
                            values (in Watts) as values
        """
        now = time.time()
        time_passed = now - self.last_update

        if time_passed > self.min_time_between_updates:
            # Not on initial call
            if self.last_update > 0 and self.api_delay > 0:
                sleeptime = random.randrange(0, self.api_delay, 1)
                logger.debug(
                    'Waiting for %d seconds before requesting new data',
                    sleeptime)
                time.sleep(sleeptime)
            try:
                self.raw_data = self._get_raw_forecast()
                self.last_update = now
            except (ConnectionError, TimeoutError) as e:
                logger.error('Error getting raw solar forecast data: %s', e)
                logger.warning('Using cached raw solar forecast data')

        forecast = self._get_forecast_from_raw_data()
        return forecast

    def _get_forecast_from_raw_data(self) -> dict[int, float]:
        """
        Process the raw data from the evcc API and return a dictionary of forecast values indexed
        by relative hour.
        """
        # Initialize prediction dictionary
        prediction = {}

        # Return empty prediction if no data available
        if not self.raw_data:
            logger.warning('No results from evcc Solar API available')
            return prediction

        # Get rates from raw data (similar to evcc tariff implementation)
        data = self.raw_data.get('rates', None)
        if data is None:
            # Fallback for older evcc versions
            data = self.raw_data.get('result', {}).get('rates', [])

        now = datetime.datetime.now().astimezone(self.timezone)

        for item in data:
            try:
                # Parse timestamp from "start" field
                timestamp = datetime.datetime.fromisoformat(item['start']).astimezone(self.timezone)
                diff = timestamp - now
                rel_hour = math.ceil(diff.total_seconds() / 3600)

                if rel_hour >= 0:
                    # Get the forecast value (likely already in Watts)
                    value = item.get('value', 0)
                    if value is None:
                        value = 0

                    # Store the value as-is (assuming evcc returns values in Watts)
                    prediction[rel_hour] = value

            except (KeyError, ValueError, TypeError) as e:
                logger.warning('Error processing forecast item %s: %s', item, e)
                continue

        # Fill missing hours with 0
        max_hour = max(prediction.keys()) if prediction else 0
        for h in range(max_hour + 1):
            if h not in prediction:
                prediction[h] = 0

        # Sort output
        output = dict(sorted(prediction.items()))
        return output

    def _get_raw_forecast(self) -> dict:
        """
        Fetch raw forecast data from evcc API.
        """
        try:
            logger.info('Requesting solar forecast from evcc API: %s', self.url)
            response = requests.get(self.url, timeout=30)
            response.raise_for_status()

            if response.status_code != 200:
                raise ConnectionError(f'[EvccSolar] API returned {response.status_code}')

        except requests.exceptions.RequestException as e:
            raise ConnectionError(f'[EvccSolar] API request failed: {e}') from e

        try:
            raw_data = response.json()
            logger.debug('Successfully retrieved raw forecast data')
            return raw_data
        except ValueError as e:
            raise ConnectionError(f'[EvccSolar] Invalid JSON response: {e}') from e


def test():
    """
    Test function for the EvccSolar class.

    Usage:
        python evcc_solar.py <url>
    """
    import sys
    import json
    import pytz

    if len(sys.argv) != 2:
        print("Usage: python evcc_solar.py <url>")
        sys.exit(1)

    url = sys.argv[1]

    # Create test configuration
    pvinstallations = [{'url': url}]
    timezone = pytz.timezone('Europe/Berlin')

    try:
        evcc_solar = EvccSolar(pvinstallations, timezone, api_delay=0)
        forecast = evcc_solar.get_forecast()
        print(json.dumps(forecast, indent=4))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test()
