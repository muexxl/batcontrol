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

class DynamicTariff:
    """ Select and configure a dynamic tariff provider based on the given configuration """
    def __new__(cls,  config:dict, timezone,min_time_between_API_calls):  # pylint: disable=invalid-name
        selected_tariff=None
        provider=config['type']

        if provider.lower()=='awattar_at':
            required_fields=['vat', 'markup', 'fees']
            for field in required_fields:
                if not field in config.keys():
                    raise RuntimeError(
                        f'[DynTariff] Please include {field} in your configuration file'
                    )
            vat = float(config['vat'])
            markup = float(config['markup'])
            fees = float(config['fees'])
            selected_tariff= Awattar(timezone,'at',min_time_between_API_calls)
            selected_tariff.set_price_parameters(vat,fees,markup)

        elif provider.lower()=='awattar_de':
            required_fields=['vat', 'markup', 'fees']
            for field in required_fields:
                if not field in config.keys():
                    raise RuntimeError(
                        f'[DynTariff] Please include {field} in your configuration file'
                    )
            vat = float(config['vat'])
            markup = float(config['markup'])
            fees = float(config['fees'])
            selected_tariff= Awattar(timezone,'de',min_time_between_API_calls)
            selected_tariff.set_price_parameters(vat,fees,markup)

        elif provider.lower()=='tibber':
            if not 'apikey' in config.keys() :
                raise RuntimeError (
                    '[Dynamic Tariff] Tibber requires an API token. '
                    'Please provide "apikey :YOURKEY" in your configuration file'
                    )
            token = config['apikey']
            selected_tariff=Tibber(timezone,token,min_time_between_API_calls)

        elif provider.lower()=='evcc':
            if not 'url' in config.keys() :
                raise RuntimeError (
                    '[Dynamic Tariff] EVCC requires an URL. '
                    'Please provide "url" in your configuration file, '
                    'like http://evcc.local/api/tariff/grid'
                    )
            selected_tariff= Evcc(timezone,config['url'],min_time_between_API_calls)
        else:
            raise RuntimeError(f'[DynamicTariff] Unkown provider {provider}')
        return selected_tariff
