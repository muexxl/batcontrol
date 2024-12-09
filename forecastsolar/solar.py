""" Factory for solar forecast providers """

from .forecastsolar_interface import ForecastSolarInterface
from .fcsolar import FCSolar

class ForecastSolar:
    """ Factory for solar forecast providers """
    @staticmethod
    def create_solar_provider(config: dict,
                              timezone,
                              requested_provider='fcsolarapi') -> ForecastSolarInterface:
        """ Select and configure a solar forecast provider based on the given configuration """

        provider = None
        if requested_provider.lower() == 'fcsolarapi':
            provider = FCSolar(config, timezone)
        else:
            raise RuntimeError(f'[ForecastSolar] Unkown provider {requested_provider}')
        return provider
