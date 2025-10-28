""" Parent Class for implementing different tariffs"""
import time
import random
import logging
from .dynamictariff_interface import TariffInterface
from ..fetcher.relaxed_caching import RelaxedCaching, CacheMissError


logger = logging.getLogger(__name__)

class DynamicTariffBaseclass(TariffInterface):
    """ Parent Class for implementing different tariffs
        # min_time_between_API_calls: Minimum time between API calls in seconds
    """
    def __init__(self, timezone,min_time_between_API_calls, delay_evaluation_by_seconds) -> None:  #pylint: disable=invalid-name
        self.raw_data={}
        self.next_update_ts=0
        self.min_time_between_updates=min_time_between_API_calls
        self.timezone=timezone
        self.delay_evaluation_by_seconds=delay_evaluation_by_seconds
        self.cache = RelaxedCaching()

    def get_raw_data(self) -> dict:
        """ Get raw data from cache or provider """
        return self.cache.get_last_entry()

    def store_raw_data(self, data: dict) -> None:
        """ Store raw data in cache """
        self.cache.store_new_entry(data)

    def refresh_data(self) -> None:
        """ Refresh data from provider if needed """
        now = time.time()
        if now  > self.next_update_ts:
            # Not on initial call
            if self.next_update_ts > 0 and self.delay_evaluation_by_seconds > 0:
                sleeptime = random.randrange(0, self.delay_evaluation_by_seconds, 1)
                logger.debug(
                    'Waiting for %d seconds before requesting new data',
                    sleeptime)
                time.sleep(sleeptime)
            try:
                self.store_raw_data(self.get_raw_data_from_provider())
                self.next_update_ts = now + self.min_time_between_updates
            except (ConnectionError, TimeoutError) as e:
                logger.error('Error getting raw tariff data: %s', e)
                logger.warning('Using cached raw tariff data')

    def get_prices(self) -> dict[int, float]:
        """ Get prices from provider """
        self.refresh_data()
        prices = self.get_prices_from_raw_data()
        return prices

    def get_raw_data_from_provider(self) -> dict:
        """ Prototype for get_raw_data_from_provider and store in cache """
        raise RuntimeError("[Dyn Tariff Base Class] Function "
                           "'get_raw_data_from_provider' not implemented"
                           )

    def get_prices_from_raw_data(self) -> dict[int, float]:
        """ Prototype for get_prices_from_raw_data """
        raise RuntimeError("[Dyn Tariff Base Class] Function "
                           "'get_prices_from_raw_data' not implemented"
                           )
