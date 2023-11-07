#! /usr/bin/env python
# %%
import pytz
import datetime
import time
import os
import yaml
import numpy as np
import logging
import sys

loglevel = logging.DEBUG
logger = logging.getLogger(__name__)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                              "%Y-%m-%d %H:%M:%S")
# filehandler = logging.FileHandler('batcontrol.log')
# filehandler.setFormatter(formatter)
# logger.addHandler(filehandler)

streamhandler = logging.StreamHandler(sys.stdout)
streamhandler.setFormatter(formatter)

logger.addHandler(streamhandler)

logger.setLevel(loglevel)

from forecastconsumption import forecastconsumption
from forecastsolar import forecastsolar
from tibber import tibber
from fronius import fronius

CONFIGFILE = "config/batcontrol_config.yaml"
ERROR_IGNORE_TIME = 600
TIME_BETWEEN_EVALUATIONS = 120

logger.info(f'[Main] Starting Batcontrol ')


class Batcontrol(object):
    def __init__(self, configfile, is_simulation=False):
        self.load_config(configfile)
        config = self.config

        timezone = pytz.timezone(config['timezone'])
        self.timezone = timezone

        self.is_simulation = is_simulation

        tibber_token = config['utility']['apikey']
        self.tibber = tibber.Tibber(tibber_token, timezone)

        fronius_address = config['inverter']['address']
        fronius_user = config['inverter']['user']
        fronius_password = config['inverter']['password']

        self.inverter = fronius.FroniusWR(
            fronius_address, fronius_user, fronius_password)

        self.pvsettings = config['pvinstallations']
        self.fc_solar = forecastsolar.ForecastSolar(self.pvsettings, timezone)

        self.load_profile = config['consumption_forecast']['load_profile']
        try:
            annual_consumption = config['consumption_forecast']['annual_consumption']
        except KeyError:
            # default setting
            annual_consumption = 0

        self.fc_consumption = forecastconsumption.ForecastConsumption(
            self.load_profile, timezone, annual_consumption)

        self.config = config['battery_control']
        self.time_at_forecast_error=-1

    def __del__(self):
        try:
            del self.inverter
        except:
            pass

    def load_config(self, configfile):

        if not os.path.isfile(configfile):
            raise RuntimeError(f'Configfile {configfile} not found')

        with open(configfile, 'r') as f:
            config_str = f.read()

        config = yaml.safe_load(config_str)

        if config['utility']['type'] == 'tibber':
            pass
        else:
            raise RuntimeError('Unkonwn Utility')

        if config['inverter']['type'] == 'fronius_gen24':
            pass
        else:
            raise RuntimeError('Unkown inverter')

        if config['pvinstallations']:
            pass
        else:
            raise RuntimeError('No PV Installation found')

        try:
            config['consumption_forecast']['load_profile'] = 'config/' + \
                config['consumption_forecast']['load_profile']
        except:
            logger.info(
                f"[Config] No load profile provided. Proceeding with default profile from default_load_profile.csv")
            config['consumption_forecast']['load_profile'] = 'default_load_profile.csv'
        
        if not os.path.isfile(config['consumption_forecast']['load_profile']):
            raise RuntimeError(
                f"[Config] Specified Load Profile file '{config['consumption_forecast']['load_profile']}' not found")

        try:
            tzstring = config['timezone']
        except KeyError:
            raise RuntimeError(
                'No entry for time zone found under general:timezone')
        try:
            tz = pytz.timezone(tzstring)
        except pytz.exceptions.UnknownTimeZoneError:
            raise RuntimeError(
                f"Config Entry in general: timezone {config['timezone']} not valid. Try e.g. 'Europe/Berlin'")
        try:
            loglevel=config['loglevel']
        except KeyError:
            loglevel='info'
            
        if loglevel=='debug':
            logger.setLevel(logging.DEBUG)
        elif loglevel =='warning':
            logger.setLevel(logging.WARNING)
        elif loglevel =='error':
            logger.setLevel(logging.ERROR)
        elif loglevel =='info':
            logger.setLevel(logging.INFO)
        else :
            logger.setLevel(logging.INFO)
            logger.info(f'[BATCtrl] Provided loglevel "{loglevel}" not valid. Defaulting to loglevel "info"')
            
        self.config = config

    def reset_forecast_error(self):
        self.time_at_forecast_error=-1
    
    def handle_forecast_error(self):
        now=time.time()
        
        #set time_at_forecast_error if it is at the default value of -1
        if self.time_at_forecast_error == -1:
            self.time_at_forecast_error=now
        
        # get time delta since error
        time_passed= now-self.time_at_forecast_error
        
        if time_passed < ERROR_IGNORE_TIME :
            #keep current mode
            logger.info(f"[BatCtrl] An API Error occured {time_passed:.0f}s ago. Keeping inverter mode unchanged.")          
        else:
            #set default mode
            logger.warning(f"[BatCtrl] An API Error occured {time_passed:.0f}s ago. Setting inverter to default mode (Allow Discharging)")
            self.inverter.set_mode_allow_discharge()
    
    def run(self):

        #get forecasts
        try:
            price_dict = self.tibber.get_prices()
            production_forecast = self.fc_solar.get_forecast()      
            # harmonize forecast horizon
            fc_period = min(max(price_dict.keys()), max(production_forecast.keys()))
            consumption_forecast = self.fc_consumption.get_forecast(fc_period+1)
        except Exception as e:
            logger.warning(f'[BatCtrl] Following Exception occurred when trying to get forecasts: \n\t{e}')
            self.handle_forecast_error()
            return
            
        self.reset_forecast_error()
        
        
        #initialize arrays
        net_consumption = np.zeros(fc_period+1)
        production = np.zeros(fc_period+1)
        consumption = np.zeros(fc_period+1)
        prices = np.zeros(fc_period+1)

        for h in range(fc_period+1):
            production[h] = production_forecast[h]
            consumption[h] = consumption_forecast[h]
            prices[h] = price_dict[h]

        # ##remove later .. for testing only
        # production = np.array([0.0, 0.0, 10.0, 84.0, 209.0, 306.0, 364.0, 396.0, 388.0, 358.0, 302.0, 209.0, 11.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # consumption = np.array([204.70490011, 185.31730578, 443.84659586, 556.12060001, 491.22851159, 
        #                 517.71839668, 438.69218739, 554.47133462, 490.90137988, 561.20282996,
        #                 519.94881476, 374.33791913, 457.29143499, 493.78277419, 474.20234129,
        #                 408.80821079, 366.37285727, 241.7048589,  184.14018146])
        
        # prices = np.array([0.159, 0.1591, 0.1594, 0.1594, 0.1594, 0.1592, 0.1593, 0.1594, 0.1602, 0.1714, 0.2071, 0.251, 0.2593, 0.251, 0.2396, 0.2334, 0.2237, 0.2212, 0.2051])
        # price_dict={}
        # for i in range(len(prices)):
        #     price_dict[i]=prices[i]
        
        ##/ remove later .. for testing only
        
        
        net_consumption = consumption-production
        logger.debug(f'[BatCTRL] Production FCST {production}')
        logger.debug(f'[BatCTRL] Consumption FCST {consumption}')
        logger.debug(f'[BatCTRL] Net Consumption FCST {net_consumption}')
        logger.debug(f'[BatCTRL] prices {prices}')
        # negative = charging or feed in
        # positive = dis-charging or grid consumption

        # correction for time that has already passed since the start of the current hour
        net_consumption[0] *= 1 - \
            datetime.datetime.now().astimezone(self.timezone).minute/60
        self.set_wr_parameters(self.inverter, net_consumption, price_dict)

        # %%
    def set_wr_parameters(self, wr: fronius.FroniusWR, net_consumption: np.ndarray, prices: dict):
        # ensure availability of data
        max_hour = min(len(net_consumption), len(prices))

        # current price as reference
        current_price = prices[0]
        mode = ""
        value = 0

        if self.is_discharge_allowed(wr, net_consumption, prices):
            logger.debug(f'[BatCTRL] Mode: Allow Discharging')
            wr.set_mode_allow_discharge()

        else:  # discharge not allowed
            charging_limit = self.config['max_charging_from_grid_limit']
            required_recharge_energy = self.get_required_required_recharge_energy(
                wr, net_consumption[:max_hour], prices)
            is_charging_possible = wr.get_SOC() < (wr.max_soc*charging_limit)

            logger.debug('[BatCTRL] Discharging is NOT allowed')
            logger.debug(f'[BatCTRL] Charging allowed: {is_charging_possible}')
            logger.debug(
                f'[BatCTRL] Energy required: {required_recharge_energy:0.1f} Wh')
            # charge if battery capacity available and more stored energy is required
            if is_charging_possible and required_recharge_energy > 0:
                remaining_time = (
                    60-datetime.datetime.now().astimezone(self.timezone).minute)/60
                charge_rate = required_recharge_energy/remaining_time
                charge_rate = min(charge_rate, wr.max_charge_rate)
                wr.set_mode_force_charge(round(charge_rate))
                logger.debug(
                    f'[BatCTRL] Mode: grid charging. Charge rate : {charge_rate} W')

            else:  # keep current charge level. recharge if solar surplus available
                wr.set_mode_avoid_discharge()
                logger.debug(f'[BatCTRL] Mode: Avoid discharge')

        return

    # %%
    def get_required_required_recharge_energy(self, wr: fronius.FroniusWR, net_consumption: list, prices: dict):
        current_price = prices[0]
        max_hour = len(net_consumption)
        consumption = np.array(net_consumption)
        consumption[consumption < 0] = 0

        production = -np.array(net_consumption)
        production[production < 0] = 0
        min_price_difference = self.config['min_price_difference']

        # evaluation period until price is first time lower then current price
        for h in range(1, max_hour):
            future_price = prices[h]
            if future_price <= current_price:
                max_hour = h
                break

        # get high price hours
        high_price_hours = []
        for h in range(max_hour):
            future_price = prices[h]
            if future_price > current_price+min_price_difference:
                high_price_hours.append(h)

        # start with latest hour
        high_price_hours.sort()
        high_price_hours.reverse()
        required_energy = 0
        for high_price_hour in high_price_hours:
            energy_to_shift = consumption[high_price_hour]

            # correct energy to shift with potential production
            # start with latest hour
            for hour in list(range(high_price_hour))[::-1]:
                if production[hour] == 0:
                    continue
                if production[hour] >= energy_to_shift:
                    production[hour] -= energy_to_shift
                    energy_to_shift = 0
                else:
                    energy_to_shift -= production[hour]
                    production[hour]
            # add_remaining energy to shift to recharge amount
            required_energy += energy_to_shift

        recharge_energy =  required_energy-wr.get_stored_energy()
        free_capacity = wr.get_free_capacity()
        
        if recharge_energy > free_capacity:
            recharge_energy=free_capacity
        if recharge_energy <0: 
            recharge_energy =0
            
        return recharge_energy

# %%

    def is_discharge_allowed(self, wr: fronius.FroniusWR, net_consumption: np.ndarray, prices: dict):
        # always allow discharging when battery is >90% maxsoc
        allow_discharge_limit = self.config['always_allow_discharge_limit']
        discharge_limit = wr.max_soc*allow_discharge_limit
        soc = wr.get_SOC()
        if soc > discharge_limit:
            logger.debug(
                f'[BatCTRL] Battery level ({soc}) above discharge limit {discharge_limit}')
            return True

        current_price = prices[0]
        min_price_difference = self.config['min_price_difference']
        max_hour = len(net_consumption)
        # relevant time range : until next recharge possibility
        for h in range(1, max_hour):
            future_price = prices[h]
            if future_price <= current_price-min_price_difference:
                max_hour = h
                break
        dt = datetime.timedelta(hours=max_hour-1)
        t0 = datetime.datetime.now()
        t1 = t0+dt
        last_hour = t1.astimezone(self.timezone).strftime("%H:59")
        logger.debug(
            f'[BatCTRL] Evaluating next {max_hour} hours until {last_hour}')
        # distribute remaining energy
        consumption = np.array(net_consumption)
        consumption[consumption < 0] = 0

        production = -np.array(net_consumption)
        production[production < 0] = 0

        # get hours with higher price
        higher_price_hours = []
        for h in range(max_hour):
            future_price = prices[h]
            if future_price > current_price:  # !!! different formula compared to detect relevant hours
                higher_price_hours.append(h)

        higher_price_hours.sort()
        higher_price_hours.reverse()

        reserved_storage = 0
        for higher_price_hour in higher_price_hours:
            if consumption[higher_price_hour] == 0:
                continue
            required_energy = consumption[higher_price_hour]

            # correct reserved_storage with potential production
            # start with latest hour
            for hour in list(range(higher_price_hour))[::-1]:
                if production[hour] == 0:
                    continue
                if production[hour] >= required_energy:
                    production[hour] -= required_energy
                    required_energy = 0
                    break
                else:
                    required_energy -= production[hour]
                    production[hour] = 0
            # add_remaining required_energy to reserved_storage
            reserved_storage += required_energy

        stored_energy = wr.get_stored_energy()
        logger.debug(
            f"[BatCTRL] Reserved Energy: {reserved_storage:0.1f} Wh. Available in Battery: {stored_energy:0.1f}Wh")
        if (stored_energy > reserved_storage):
            # allow discharging
            return True
        else:
            # forbid discharging
            return False


if __name__ == '__main__':
    bc = Batcontrol(CONFIGFILE)
    try:
        while (1):
            bc.run()
            time.sleep(TIME_BETWEEN_EVALUATIONS)
    finally:
        del bc
