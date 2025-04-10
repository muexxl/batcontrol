"""
DynamicTariff class to select and configure a dynamic tariff provider based
     on the given configuration.

Args:
    config (dict): Configuration dictionary containing the provider type and necessary parameters.
    timezone (str): Timezone information.
    min_time_between_API_calls (int): Minimum time interval between API calls.

Returns:
    selected_tariff: An instance of the selected tariff provider class (Awattar, Tibber, or Evcc).

Raises:
    RuntimeError: If required fields are missing in the configuration
                     or if the provider type is unknown.
"""
from .awattar import Awattar
from .tibber import Tibber
from .evcc import Evcc
from .dynamictariff_interface import TariffInterface

class DynamicTariff:
    """ DynamicTariff factory"""
    @staticmethod
    def create_tarif_provider(config:dict, timezone,
                              min_time_between_api_calls,
                              delay_evaluation_by_seconds
                              ) -> TariffInterface:
        """ Select and configure a dynamic tariff provider based on the given configuration """
        selected_tariff=None
        provider=config.get('type')

        if provider.lower()=='awattar_at':
            required_fields=['vat', 'markup', 'fees']
            for field in required_fields:
                if not field in config.keys():
                    raise RuntimeError(
                        f'[DynTariff] Please include {field} in your configuration file'
                    )
            vat = float(config.get('vat',0))
            markup = float(config.get('markup',0))
            fees = float(config.get('fees',0))
            selected_tariff= Awattar(timezone,'at',
                                     min_time_between_api_calls,
                                     delay_evaluation_by_seconds
                                    )
            selected_tariff.set_price_parameters(vat,fees,markup)

        elif provider.lower()=='awattar_de':
            required_fields=['vat', 'markup', 'fees']
            for field in required_fields:
                if not field in config.keys():
                    raise RuntimeError(
                        f'[DynTariff] Please include {field} in your configuration file'
                    )
            vat = float(config.get('vat',0))
            markup = float(config.get('markup',0))
            fees = float(config.get('fees',0))
            selected_tariff= Awattar(timezone,'de',
                                     min_time_between_api_calls,
                                     delay_evaluation_by_seconds
                                     )
            selected_tariff.set_price_parameters(vat,fees,markup)

        elif provider.lower()=='tibber':
            if not 'apikey' in config.keys() :
                raise RuntimeError (
                    '[Dynamic Tariff] Tibber requires an API token. '
                    'Please provide "apikey :YOURKEY" in your configuration file'
                    )
            token = config.get('apikey')
            selected_tariff=Tibber(timezone,
                                   token,
                                   min_time_between_api_calls,
                                   delay_evaluation_by_seconds
                                   )

        elif provider.lower()=='evcc':
            if not 'url' in config.keys() :
                raise RuntimeError (
                    '[Dynamic Tariff] evcc requires an URL. '
                    'Please provide "url" in your configuration file, '
                    'like http://evcc.local/api/tariff/grid'
                    )
            selected_tariff= Evcc(timezone,config.get('url'),min_time_between_api_calls)
        else:
            raise RuntimeError(f'[DynamicTariff] Unkown provider {provider}')
        return selected_tariff
