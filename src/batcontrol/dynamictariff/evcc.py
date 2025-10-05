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
            If multiple price entries are provided for the same hour (e.g., every 15 minutes),
            the hourly price is calculated as the average of all entries for that hour.
        """
        data=self.raw_data.get('rates', None)
        if data is None:
            #prior to evcc 0.207.0 the rates were in the 'result' field
            data=self.raw_data['result']['rates']

        now=datetime.datetime.now().astimezone(self.timezone)
        current_hour_start=now.replace(minute=0, second=0, microsecond=0)

        # Store all prices for each hour to calculate average
        hourly_prices={}

        for item in data:
            # "start":"2024-06-20T08:00:00+02:00" to timestamp
            timestamp=datetime.datetime.fromisoformat(item['start']).astimezone(self.timezone)
            # Calculate relative hour based on hour boundaries
            hour_start=timestamp.replace(minute=0, second=0, microsecond=0)
            diff_hours=(hour_start-current_hour_start).total_seconds()/3600
            rel_hour=int(diff_hours)

            if rel_hour >=0:
                # since evcc 0.203.0 value is the name of the price field.
                if item.get('value', None) is not None:
                    price=item['value']
                else:
                    price=item['price']

                # Collect all prices for each hour
                if rel_hour not in hourly_prices:
                    hourly_prices[rel_hour]=[]
                hourly_prices[rel_hour].append(price)

        # Calculate average price for each hour
        prices={}
        for rel_hour, price_list in hourly_prices.items():
            prices[rel_hour]=sum(price_list)/len(price_list)

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
