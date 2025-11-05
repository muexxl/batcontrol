""" Parent Class for implementing different solar forecast providers"""
import threading
import time
import random
import logging
import schedule
from .forecastsolar_interface import ForecastSolarInterface
from ..fetcher.relaxed_caching import RelaxedCaching, CacheMissError


logger = logging.getLogger(__name__)

class ProviderError(Exception):
    """Exception raised when there's an error with the forecast provider."""
    pass


class RateLimitException(ProviderError):
    """Exception raised when the provider's rate limit is exceeded."""
    pass

class ForecastSolarBaseclass(ForecastSolarInterface):
    """ Parent Class for implementing different solar forecast providers
        # min_time_between_API_calls: Minimum time between API calls in seconds
    """
    def __init__(self, pvinstallations, timezone, min_time_between_API_calls, delay_evaluation_by_seconds) -> None:
        self.pvinstallations = pvinstallations
        self.next_update_ts = 0
        self.min_time_between_updates = min_time_between_API_calls
        self.timezone = timezone
        self.delay_evaluation_by_seconds = delay_evaluation_by_seconds
        self.cache_list = {}
        self.rate_limit_blackout_window_ts = 0
        self._refresh_data_lock = threading.Lock()

        try:
            for unit in pvinstallations:
                name = unit['name']
                self.cache_list[name] = RelaxedCaching()
        except KeyError as e:
            raise ValueError("Each PV installation must have a 'name' key") from e

    def get_raw_data(self, pvinstallation_name) -> dict:
        """ Get raw data from cache or provider """
        return self.cache_list[pvinstallation_name].get_last_entry()

    def get_all_raw_data(self) -> dict:
        """ Get raw data for all installations from cache """
        all_data = {}
        for unit in self.pvinstallations:
            name = unit['name']
            all_data[name] = self.get_raw_data(name)
        return all_data

    def store_raw_data(self, pvinstallation_name, data: dict) -> None:
        """ Store raw data in cache """
        self.cache_list[pvinstallation_name].store_new_entry(data)

    def refresh_data(self) -> None:
        """ Refresh data from provider if needed """
        with self._refresh_data_lock:
            now = time.time()

            if now > self.next_update_ts:
                if self.rate_limit_blackout_window_ts > now:
                    logger.info(
                        'Rate limit blackout window in place until %s (another %d seconds)',
                        self.rate_limit_blackout_window_ts,
                        self.rate_limit_blackout_window_ts - now
                    )
                    self.next_update_ts = self.rate_limit_blackout_window_ts
                    return

                # Not on initial call
                if self.next_update_ts > 0 and self.delay_evaluation_by_seconds > 0:
                    sleeptime = random.randrange(0, self.delay_evaluation_by_seconds, 1)
                    logger.debug(
                        'Waiting for %d seconds before requesting new data',
                        sleeptime)
                    time.sleep(sleeptime)
                try:
                    for unit in self.pvinstallations:
                        name = unit['name']
                        result = self.get_raw_data_from_provider(name)
                        try:
                            # Store raw data only if no CacheMissError occurred
                            self.store_raw_data(name, result)
                        except RateLimitException:
                            logger.warning(
                                'Rate limit exceeded. Setting blackout window until %s',
                                self.rate_limit_blackout_window_ts)
                    self.next_update_ts = now + self.min_time_between_updates
                except (ConnectionError, TimeoutError, ProviderError) as e:
                    logger.error('Error getting raw solar forecast data: %s', e)
                    logger.warning('Using cached raw solar forecast data')

    def get_forecast(self) -> dict[int, float]:
        """ Get forecast from provider """
        self.refresh_data()
        forecast = self.get_forecast_from_raw_data()

        max_hour=max(forecast.keys())
        if max_hour < 18:
            logger.error('Less than 18 hours of forecast data. Stopping.')
            raise RuntimeError('Less than 18 hours of forecast data.')

        return forecast

    def get_raw_data_from_provider(self, pvinstallation_name) -> dict:
        """ Prototype for get_raw_data_from_provider and store in cache """
        raise RuntimeError("[Forecast Solar Base Class] Function "
                           "'get_raw_data_from_provider' not implemented"
                           )

    def get_forecast_from_raw_data(self) -> dict[int, float]:
        """ Prototype for get_forecast_from_raw_data """
        raise RuntimeError("[Forecast Solar Base Class] Function "
                           "'get_forecast_from_raw_data' not implemented"
                           )
