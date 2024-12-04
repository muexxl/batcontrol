"""Awattar Class

This module implements the Awattar API to retrieve dynamic electricity prices.
It inherits from the DynamicTariffBaseclass.

Classes:
    Awattar: A class to interact with the Awattar API and process electricity prices.

Methods:
    __init__(self,
                timezone, country: str,
                price_fees: float,
                price_markup: float,
                vat: float,
                min_time_between_API_calls=0):

        Initializes the Awattar class with the specified parameters.

    get_raw_data_from_provider(self):
        Fetches raw data from the Awattar API.

    get_prices_from_raw_data(self):
        Processes the raw data to extract and calculate electricity prices.
"""
import datetime
import math
import requests
from .baseclass import DynamicTariffBaseclass

class Awattar(DynamicTariffBaseclass):
    """ Implement Awattar API to get dynamic electricity prices
        Inherits from DynamicTariffBaseclass
    """

    def __init__(self, timezone ,country:str, min_time_between_API_calls=0, delay_evaluation_by_seconds=0):
        super().__init__(timezone,min_time_between_API_calls, delay_evaluation_by_seconds)
        country= country.lower()
        if country in ['at','de']:
            self.url=f'https://api.awattar.{country}/v1/marketdata'
        else:
            raise RuntimeError(f'[Awattar] Country Code {country} not known')

        self.vat=0
        self.price_fees=0
        self.price_markup=0

    def set_price_parameters(self, vat:float, price_fees:float, price_markup:float):
        """ Set the extra price parameters for the tariff calculation """
        self.vat=vat
        self.price_fees=price_fees
        self.price_markup=price_markup

    def get_raw_data_from_provider(self):
        response=requests.get(self.url, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f'[Awattar_AT] API returned {response}')

        raw_data=response.json()
        return raw_data


    def get_prices_from_raw_data(self):
        data=self.raw_data['data']
        now=datetime.datetime.now().astimezone(self.timezone)
        prices={}
        for item in data:
            timestamp=datetime.datetime.fromtimestamp(
                            item['start_timestamp']/1000).astimezone(self.timezone
                        )
            diff=timestamp-now
            rel_hour=math.ceil(diff.total_seconds()/3600)
            if rel_hour >=0:
                end_price=( item['marketprice']/1000*(1+self.price_markup) + self.price_fees
                          ) * (1+self.vat)
                prices[rel_hour]=end_price
        return prices
