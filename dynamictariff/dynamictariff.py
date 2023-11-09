
from .awattar import Awattar
from .tibber import Tibber
class DynamicTariff(object):
    def __new__(cls,  provider:str, timezone, min_time_between_API_calls=0, token=None):
        selected_tariff=None
        if provider.lower()=='awattar_at':
            selected_tariff= Awattar(timezone,'at',min_time_between_API_calls)
        elif provider.lower()=='awattar_de':
            selected_tariff= Awattar(timezone,'de',min_time_between_API_calls)
        elif provider.lower()=='tibber':
            if not token:
                raise RuntimeError (f'[Dynamic Tariff] Tibber requires an API token. No token provided')
            selected_tariff=Tibber(timezone,token,min_time_between_API_calls)
        else:
            raise RuntimeError(f'[DynamicTariff] Unkown provider {provider}')
        return selected_tariff
        