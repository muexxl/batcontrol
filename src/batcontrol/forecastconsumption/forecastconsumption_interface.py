""" Interface for consumption forecast classes """

from abc import ABC, abstractmethod

class ForecastConsumptionInterface(ABC):
    """ Interface for ConsumptionAPI classes """

    @abstractmethod
    def get_forecast(self, hours) -> dict[int, float]:
        """ Get consumption forecast up to next 48 hours """
