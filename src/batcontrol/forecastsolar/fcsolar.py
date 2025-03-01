""" Module to get forecast from Forecast Solar API

See https://forecast.solar/ for more information

"""

import datetime
import random
import time
import math
import json
import logging
import requests
from .forecastsolar_interface import ForecastSolarInterface

logger = logging.getLogger('__main__')
logger.info('[FCSolar] loading module')

class FCSolar(ForecastSolarInterface):
    """ Provider to get data from https://forecast.solar/ """
    def __init__(self, pvinstallations, timezone,
                 delay_evaluation_by_seconds) -> None:
        self.pvinstallations = pvinstallations
        self.results = {}
        self.last_update = 0
        self.seconds_between_updates = 900
        self.timezone=timezone
        self.rate_limit_blackout_window = 0
        self.delay_evaluation_by_seconds=delay_evaluation_by_seconds

    def get_forecast(self) -> dict:
        """ Get hourly forecast from provider """
        got_error = False
        t0 = time.time()
        dt = t0-self.last_update
        if dt > self.seconds_between_updates:
            if self.rate_limit_blackout_window < t0:
                try:
                    if self.last_update > 0 and self.delay_evaluation_by_seconds > 0:
                        sleeptime = random.randrange(0, self.delay_evaluation_by_seconds, 1)
                        logger.debug(
                            '[FCSolar] Waiting for %d seconds before requesting new data',
                            sleeptime)
                        time.sleep(sleeptime)
                    self.__get_raw_forecast()
                    self.last_update = t0
                except Exception as e:
                    # Catch error here.
                    # Check cached values below
                    logger.error('[FCSolar] Error getting forecast: %s', e)
                    logger.warning('[FCSolar] Using cached values')
                    got_error = True
            else:
                remaining_time = self.rate_limit_blackout_window - t0
                logger.info(
                    '[FCSolar] Rate limit blackout window in place until %s (another %d seconds)',
                      self.rate_limit_blackout_window,
                      remaining_time
                )
        prediction = {}
        for hour in range(48+1):
            prediction[hour] = 0

        # return empty prediction if results have not been obtained
        if not self.results:
            logger.warning('[FCSolar] No results from FC Solar API available')
            raise RuntimeWarning('[FCSolar] No results from FC Solar API available')

        prediction={}
        now = datetime.datetime.now().astimezone(self.timezone)
        current_hour = datetime.datetime(
            now.year, now.month, now.day, now.hour).astimezone(self.timezone)
        result = next(iter(self.results.values()))
        response_time_string = result['message']['info']['time']
        response_time = datetime.datetime.fromisoformat(response_time_string)
        response_timezone = response_time.tzinfo
        for _, result in self.results.items():
            for isotime, value in result['result'].items():
                timestamp = datetime.datetime.fromisoformat(
                    isotime).astimezone(response_timezone)
                diff = timestamp-current_hour
                rel_hour = math.ceil(diff.total_seconds()/3600)-1
                if rel_hour >= 0:
                    if rel_hour in prediction.keys():
                        prediction[rel_hour] += value
                    else:
                        prediction[rel_hour] = value

        max_hour=max(prediction.keys())
        if max_hour < 18 and got_error:
            logger.error('[FCSolar] Less than 18 hours of forecast data. Stopping.')
            raise RuntimeError('[FCSolar] Less than 18 hours of forecast data.')
        #complete hours without production with 0 values
        for h in range(max_hour+1):
            if h not in prediction.keys():
                prediction[h]=0
        #sort output
        output=dict(sorted(prediction.items()))

        return output

    def __get_raw_forecast(self):
        unit: dict
        for unit in self.pvinstallations:
            name = unit['name']
            lat = unit['lat']
            lon = unit['lon']
            dec = unit['declination']  # declination
            az = unit['azimuth']  # 90 =W -90 = E
            kwp = unit['kWp']

            apikey_urlmod=''
            if 'apikey' in unit.keys() and unit['apikey'] is not None:
                apikey_urlmod = unit['apikey'] +"/"# ForecastSolar api
            #legacy naming in config file
            elif 'api' in unit.keys() and unit['api'] is not None:
                apikey_urlmod = unit['api'] +"/" # ForecastSolar api

            horizon_querymod = ''
            if 'horizon' in unit.keys() and unit['horizon'] is not None:
                horizon_querymod = "?horizon=" + unit['horizon']  # ForecastSolar api

            url = (f"https://api.forecast.solar/{apikey_urlmod}estimate/"
                   f"watthours/period/{lat}/{lon}/{dec}/{az}/{kwp}{horizon_querymod}")
            logger.info(
                '[FCSolar] Requesting Information for PV Installation %s', name)


            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                self.results[name] = json.loads(response.text)
            elif response.status_code == 429:
                retry_after = response.headers.get('X-Ratelimit-Retry-At')
                if retry_after:
                    retry_after_timestamp = datetime.datetime.fromisoformat(retry_after)
                    now = datetime.datetime.now().astimezone(self.timezone)
                    retry_seconds = (retry_after_timestamp - now).total_seconds()
                    self.rate_limit_blackout_window = retry_after_timestamp.timestamp()
                    logger.warning(
                      '[ForecastSolar] forecast solar API rate limit exceeded [%s]. '
                      'Retry after %d seconds at %s',
                      response.text,
                      retry_seconds,
                      retry_after_timestamp
                    )
                else:
                    logger.warning(
                        '[ForecastSolar] forecast solar API rate limit exceeded [%s]. '
                        'No retry after information available, dumping headers',
                        response.text
                    )
                    for header, value in response.headers.items():
                        logger.debug('[ForecastSolar 429] Header: %s = %s', header, value)

            else:
                logger.warning(
                    '[ForecastSolar] forecast solar API returned %s - %s',
                      response.status_code, response.text)

if __name__ == '__main__':
    test_pvinstallations = [{'name': 'Nordhalle',
                        'lat': '49.632461',
                        'lon': '8.617459',
                        'declination': '15',
                        'azimuth': '-1',
                        'kWp': '75.695'},
                       {'name': 'Suedhalle',
                           'lat': '49.6319',
                           'lon': '8.6175',
                           'declination': '20',
                           'azimuth': '7',
                           'kWp': '25.030'}]
    fcs=FCSolar( test_pvinstallations, 'Europe/Berlin' , 10)
    print (fcs.get_forecast())
