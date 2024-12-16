""" Interface for solar forecast classes """

from abc import ABC, abstractmethod

class ForecastSolarInterface(ABC):
    """ Interface for SolarAPI classes """
    @abstractmethod
    def __init__(self, pvinstallations, timezone, api_delay):
        """ Initialize the SolarAPI class """

    @abstractmethod
    def get_forecast(self) -> dict[int, float]:
        """ Get solar production of all installations up to next 48 hours """