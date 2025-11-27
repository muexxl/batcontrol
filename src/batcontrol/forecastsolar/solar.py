""" Factory for solar forecast providers """

from .forecastsolar_interface import ForecastSolarInterface
from .fcsolar import FCSolar
from .solarprognose import SolarPrognose
from .evcc_solar import EvccSolar


class ForecastSolar:
    """ Factory for solar forecast providers """
    @staticmethod
    def create_solar_provider(config: dict,
                              timezone,
                              min_time_between_api_calls,
                              api_delay=0,
                              requested_provider='fcsolarapi',
                              full_config: dict = None) -> ForecastSolarInterface:
        """ Select and configure a solar forecast provider based on the given configuration 

        Args:
            config: PV installations configuration (pvinstallations)
            timezone: Timezone for forecast data
            min_time_between_api_calls: Minimum seconds between API calls
            api_delay: Delay for API evaluation
            requested_provider: Provider name
            full_config: Full configuration dict (for accessing time_resolution_minutes)
        """
        # Extract target resolution from full config
        target_resolution = 60  # Default
        if full_config:
            target_resolution = full_config.get('time_resolution_minutes', 60)

        provider = None
        if requested_provider.lower() == 'fcsolarapi':
            provider = FCSolar(config, timezone, min_time_between_api_calls,
                               api_delay, target_resolution)
        elif requested_provider.lower() == 'solarprognose':
            provider = SolarPrognose(
                config, timezone, min_time_between_api_calls, api_delay, target_resolution)
        elif requested_provider.lower() == 'evcc-solar':
            provider = EvccSolar(config, timezone, min_time_between_api_calls,
                                 api_delay, target_resolution)
        else:
            raise RuntimeError(f'[ForecastSolar] Unkown provider {requested_provider}')
        return provider
