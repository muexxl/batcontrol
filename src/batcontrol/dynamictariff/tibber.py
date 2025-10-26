""" Implement Tibber API to get dynamic electricity prices
"""

import datetime
import logging
import math
import requests
from .baseclass import DynamicTariffBaseclass

logger = logging.getLogger(__name__)

class Tibber(DynamicTariffBaseclass):
    """ Implement Tibber API to get dynamic electricity prices
        Inherits from DynamicTariffBaseclass
    """
    def __init__(self, timezone , token, min_time_between_API_calls=0, delay_evaluation_by_seconds=0):
        super().__init__(timezone,min_time_between_API_calls, delay_evaluation_by_seconds)
        self.access_token=token
        self.url="https://api.tibber.com/v1-beta/gql"

    def get_raw_data_from_provider(self) -> dict:
        """ Get raw data from Tibber API """
        logger.debug('Requesting price forecast from Tibber API')
        if not self.access_token:
            raise RuntimeError
        headers={"Authorization":"Bearer " + self.access_token,
                "Content-Type":"application/json"}
        data="""{ "query":
        "{viewer {homes {currentSubscription {priceInfo(resolution: HOURLY) { current {total startsAt } today {total startsAt } tomorrow {total startsAt }}}}}}" }
        """
        try:
            response = requests.post(self.url, data, headers=headers, timeout=30)
            response.raise_for_status()
            if response.status_code != 200:
                raise ConnectionError(f'[Tibber] API responded with {response}')
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f'[Tibber] API request failed: {e}') from e

        raw_data=response.json()
        return raw_data


    def get_prices_from_raw_data(self) -> dict[int, float]:
        """ Extract prices from raw to internal datastracture based on hours """
        homeid=0
        rawdata=self.raw_data['data']
        now=datetime.datetime.now().astimezone(self.timezone)
        prices={}
        for day in ['today', 'tomorrow']:
            dayinfo=rawdata['viewer']['homes'][homeid]['currentSubscription']['priceInfo'][day]
            for item in dayinfo:
                timestamp=datetime.datetime.fromisoformat(item['startsAt'])
                diff=timestamp-now
                rel_hour=math.ceil(diff.total_seconds()/3600)
                if rel_hour >=0:
                    prices[rel_hour]=item['total']
        return prices
