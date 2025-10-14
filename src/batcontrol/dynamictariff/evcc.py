"""
This module defines the Evcc class, which is used to interact with the evcc API to fetch
dynamic tariff data.

Classes:
    Evcc: A class to interact with the evcc API and process dynamic tariff data.

Methods:
    __init__(self, timezone, url, min_time_between_API_calls=60):
        Initializes the Evcc instance with the given timezone, API URL,
        and minimum time between API calls.

    get_raw_data_from_provider(self):
        Fetches raw data from the evcc API and returns it as a JSON object.

    get_prices_from_raw_data(self):
        Processes the raw data from the evcc API and returns a dictionary of prices
        indexed by the relative hour.

    test():
        A test function to run the Evcc class with a provided URL and print the fetched prices.


"""
import datetime
import math
import requests
from .baseclass import DynamicTariffBaseclass

class Evcc(DynamicTariffBaseclass):
    """ Implement evcc API to get dynamic electricity prices
        Inherits from DynamicTariffBaseclass
    """
    def __init__(self, timezone , url , min_time_between_API_calls=60):
        super().__init__(timezone,min_time_between_API_calls, 0)
        self.delay_evaluation_by_seconds=0
        self.url=url

    def get_raw_data_from_provider(self) -> dict:  # pylint: disable=unused-private-member
        try:
            response = requests.get(self.url, timeout=30)
            response.raise_for_status()
            if response.status_code != 200:
                raise ConnectionError(f'[evcc] API returned {response}')
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f'[evcc] API request failed: {e}') from e

        # {"result":
        #     { "rates": [
        #            {
        #                "start":"2024-06-20T08:00:00+02:00",
        #                "end":"2024-06-20T09:00:00+02:00",
        #                "price":0.35188299999999995
        #             },
        #            {
        #               "start":"2024-06-20T09:00:00+02:00",
        #                "end":"2024-06-20T10:00:00+02:00",
        #                "price":0.3253459999999999"
        #            }
        #        ]
        #     }
        # }

        raw_data=response.json()
        return raw_data


    def get_prices_from_raw_data(self) -> dict[int, float]:   # pylint: disable=unused-private-member
        """ Process the raw data from the evcc API and return a dictionary of prices indexed
            by relative hour.
            The relative hour is calculated from the current time in the specified timezone.
            If multiple prices are provided for the same hour (e.g., every 15 minutes),
            the hourly price is calculated as the average of all those entries.
        """
        data=self.raw_data.get('rates', None)
        if data is None:
            #prior to evcc 0.207.0 the rates were in the 'result' field
            data=self.raw_data['result']['rates']

        now=datetime.datetime.now().astimezone(self.timezone)
        # Get the start of the current hour
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        # Use a dictionary to collect all prices for each hour
        hourly_prices={}

        for item in data:
            # "start":"2024-06-20T08:00:00+02:00" to timestamp
            timestamp=datetime.datetime.fromisoformat(item['start']).astimezone(self.timezone)
            # Get the start of the hour for this timestamp
            interval_hour_start = timestamp.replace(minute=0, second=0, microsecond=0)
            # Calculate relative hour based on hour boundaries
            diff = interval_hour_start - current_hour_start
            rel_hour = int(diff.total_seconds() / 3600)
            if rel_hour >=0:
                # since evcc 0.203.0 value is the name of the price field.
                if item.get('value', None) is not None:
                    price=item['value']
                else:
                    price=item['price']
                
                # Collect all prices for this hour
                if rel_hour not in hourly_prices:
                    hourly_prices[rel_hour]=[]
                hourly_prices[rel_hour].append(price)
        
        # Calculate average for each hour
        prices={}
        for hour, price_list in hourly_prices.items():
            prices[hour]=sum(price_list)/len(price_list)
        
        return prices
