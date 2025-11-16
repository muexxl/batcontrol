"""Energyforecast.de Class

This module implements the energyforecast.de API to retrieve dynamic electricity prices.
It inherits from the DynamicTariffBaseclass.

Classes:
    Energyforecast: A class to interact with the energyforecast.de API
                    and process electricity prices.

Methods:
    __init__(self,
                timezone,
                price_fees: float,
                price_markup: float,
                vat: float,
                min_time_between_API_calls=0):

        Initializes the Energyforecast class with the specified parameters.

    get_raw_data_from_provider(self):
        Fetches raw data from the energyforecast.de API.

    get_prices_from_raw_data(self):
        Processes the raw data to extract and calculate electricity prices.
"""
import datetime
import logging
import math
import requests
from .baseclass import DynamicTariffBaseclass

logger = logging.getLogger(__name__)

class Energyforecast(DynamicTariffBaseclass):
    """ Implement energyforecast.de API to get dynamic electricity prices
        Inherits from DynamicTariffBaseclass

        Uses 48-hour forecast window for better day-ahead planning.
        # min_time_between_API_calls: Minimum time between API calls in seconds
    """

    def __init__(self, timezone, token, min_time_between_API_calls=0,
                 delay_evaluation_by_seconds=0):
        """ Initialize Energyforecast class with parameters """
        super().__init__(timezone, min_time_between_API_calls, delay_evaluation_by_seconds)
        self.url = 'https://www.energyforecast.de/api/v1/predictions/next_48_hours'
        self.token = token
        self.vat = 0
        self.price_fees = 0
        self.price_markup = 0

    def upgrade_48h_to_96h(self):
        """ During initialization, we can upgrade the forecast if user wants 96h horizon """
        self.url = 'https://www.energyforecast.de/api/v1/predictions/next_96_hours'

    def set_price_parameters(self, vat: float, price_fees: float, price_markup: float):
        """ Set the extra price parameters for the tariff calculation """
        self.vat = vat
        self.price_fees = price_fees
        self.price_markup = price_markup

    def get_raw_data_from_provider(self):
        """ Get raw data from energyforecast.de API and return parsed json """
        logger.debug('Requesting price forecast from energyforecast.de API')
        if not self.token:
            raise RuntimeError('[Energyforecast] API token is required')
        try:
            # Request base prices without provider-side calculations
            # We apply vat, fees, and markup locally
            params = {
                'resolution': 'hourly',
                'token': self.token,
                'vat': 0,
                'fixed_cost_cent': 0
            }
            response = requests.get(self.url, params=params, timeout=30)
            response.raise_for_status()
            if response.status_code != 200:
                raise ConnectionError(f'[Energyforecast] API returned {response}')
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f'[Energyforecast] API request failed: {e}') from e

        response_json = response.json()
        return {'data': response_json}

    def get_prices_from_raw_data(self):
        """ Extract prices from raw data to internal data structure based on hours 

        Expected API response format:
           data: [
              {
                "start": "2025-11-11T06:00:35.531Z",
                "end": "2025-11-11T06:00:35.531Z",
                "price": 0,
                "price_origin": "string"
              }
            ]

        """
        raw_data = self.get_raw_data()
        data = raw_data.get('data', [])
        now = datetime.datetime.now(self.timezone)
        prices = {}

        for item in data:
            # Parse ISO format timestamp
            # Python <3.11 does not support 'Z' (UTC) in fromisoformat(),
            # so we replace it with '+00:00'.
            # Remove this workaround if only supporting Python 3.11+.
            timestamp = datetime.datetime.fromisoformat(
                item['start'].replace('Z', '+00:00')
            ).astimezone(self.timezone)

            diff = timestamp - now
            rel_hour = math.ceil(diff.total_seconds() / 3600)

            if rel_hour >= 0:
                # Apply fees/markup/vat to the base price
                # The price field should already be in the correct unit (EUR/kWh)
                base_price = item['price']
                end_price = ((base_price * (1 + self.price_markup) + self.price_fees)
                            * (1 + self.vat))
                prices[rel_hour] = end_price

        return prices
