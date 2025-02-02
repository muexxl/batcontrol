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

Usage:
    To use this module, run it as a script with the API URL as an argument:
    python evcc.py <url>
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
        response=requests.get(self.url, timeout=30)

        if response.status_code != 200:
            raise RuntimeError(f'[evcc] API returned {response}')

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
        data=self.raw_data['result']['rates']
        now=datetime.datetime.now().astimezone(self.timezone)
        prices={}

        for item in data:
            # "start":"2024-06-20T08:00:00+02:00" to timestamp
            timestamp=datetime.datetime.fromisoformat(item['start']).astimezone(self.timezone)
            diff=timestamp-now
            rel_hour=math.ceil(diff.total_seconds()/3600)
            if rel_hour >=0:
                prices[rel_hour]=item['price']
        return prices

def test():
    """
    This script tests the functionality of the Evcc class by fetching and printing
    electric vehicle charging prices from a specified URL.

    Usage:
        python evcc.py <url>

    Arguments:
        url (str): The URL to fetch the EV charging prices from.

    The script performs the following steps:
    1. Initializes an instance of the Evcc class with the specified URL and the
       'Europe/Berlin' timezone.
    2. Fetches the EV charging prices using the get_prices method of the Evcc class.
    3. Prints the fetched prices in a formatted JSON structure.

    Dependencies:
        - sys
        - json
        - pytz
    """
    import sys  # pylint: disable=import-outside-toplevel
    import json # pylint: disable=import-outside-toplevel
    import pytz # pylint: disable=import-outside-toplevel
    if len(sys.argv) != 2:
        print("Usage: python evcc.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    evcc = Evcc(pytz.timezone('Europe/Berlin'), url)  # Assuming the Evcc constructor takes a URL

    prices = evcc.get_prices()
    print(json.dumps(prices, indent=4))

if __name__ == "__main__":
    test()
