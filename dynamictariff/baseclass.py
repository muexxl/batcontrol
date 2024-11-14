""" Parent Class for implementing different tariffs"""
import time

class DynamicTariffBaseclass:
    """ Parent Class for implementing different tariffs"""
    def __init__(self, timezone,min_time_between_API_calls) -> None:  #pylint: disable=invalid-name
        self.raw_data={}
        self.last_update=0
        self.min_time_between_updates=min_time_between_API_calls
        self.timezone=timezone

    def get_prices(self):
        """ Get prices from provider """
        now=time.time()
        time_passed=now-self.last_update
        if time_passed> self.min_time_between_updates:
            self.raw_data=self.get_raw_data_from_provider()
            self.last_update=now
        prices=self.get_prices_from_raw_data()
        return prices

    def get_raw_data_from_provider(self):
        """ Prototype for get_raw_data_from_provider """
        raise RuntimeError("[Dyn Tariff Base Class] Function "
                           "'get_raw_data_from_provider' not implemented"
                           )

    def get_prices_from_raw_data(self):
        """ Prototype for get_prices_from_raw_data """
        raise RuntimeError("[Dyn Tariff Base Class] Function "
                           "'get_prices_from_raw_data' not implemented"
                           )
