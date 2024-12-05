""" Parent Class for implementing different tariffs"""
import time
import random
import logging
from .dynamictariff_interface import TariffInterface


logger = logging.getLogger('__main__')

class DynamicTariffBaseclass(TariffInterface):
    """ Parent Class for implementing different tariffs"""
    def __init__(self, timezone,min_time_between_API_calls, delay_evaluation_by_seconds) -> None:  #pylint: disable=invalid-name
        self.raw_data={}
        self.last_update=0
        self.min_time_between_updates=min_time_between_API_calls
        self.timezone=timezone
        self.delay_evaluation_by_seconds=delay_evaluation_by_seconds

    def get_prices(self) -> dict[int, float]:
        """ Get prices from provider """
        now=time.time()
        time_passed=now-self.last_update
        if time_passed> self.min_time_between_updates:
            # Not on initial call
            if self.last_update > 0 and self.delay_evaluation_by_seconds > 0:
                sleeptime = random.randrange(0, self.delay_evaluation_by_seconds, 1)
                logger.debug(
                        '[Tariff] Waiting for %d seconds before requesting new data',
                        sleeptime)
                time.sleep(sleeptime)
            self.raw_data=self.get_raw_data_from_provider()
            self.last_update=now
        prices=self.get_prices_from_raw_data()
        return prices

    def get_raw_data_from_provider(self) -> dict:
        """ Prototype for get_raw_data_from_provider """
        raise RuntimeError("[Dyn Tariff Base Class] Function "
                           "'get_raw_data_from_provider' not implemented"
                           )

    def get_prices_from_raw_data(self) -> dict[int, float]:
        """ Prototype for get_prices_from_raw_data """
        raise RuntimeError("[Dyn Tariff Base Class] Function "
                           "'get_prices_from_raw_data' not implemented"
                           )
