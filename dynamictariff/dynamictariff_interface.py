""" Interface for tariff classes """

from abc import ABC, abstractmethod

class TariffInterface(ABC):
    """ Interface for tariff classes """
    @abstractmethod
    def __init__(self, timezone, min_time_between_api_calls, delay_evaluation_by_seconds):
        """ Initialize the tariff class """

    @abstractmethod
    def get_prices(self) -> dict[int, float]:
        """ get prices in processable format with hours as keys """
