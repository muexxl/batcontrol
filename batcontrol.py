#! /usr/bin/env python
#%%
import logging

loglevel=logging.DEBUG
logger=logging.getLogger(__name__)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                              "%Y-%m-%d %H:%M:%S")
filehandler=logging.FileHandler('batcontrol.log')
filehandler.setFormatter(formatter)
logger.addHandler(filehandler)

logger.setLevel(loglevel)

from fronius import fronius
from tibber import tibber
from forecastsolar import forecastsolar
from forecastconsumption import forecastconsumption
import numpy as np
import yaml
import os, time, datetime


logger.info(f'[Main] Starting Batcontrol ')



class Batcontrol(object):
    def __init__(self, configfile, is_simulation=False):
        self.load_config(configfile)
        config=self.config
        
        self.is_simulation=is_simulation
        
        tibber_token=config['utility']['apikey']
        self.tibber = tibber.Tibber(tibber_token)
        
        fronius_address=config['inverter']['address']
        fronius_user = config['inverter']['user']
        fronius_password = config['inverter']['password']
        
        self.inverter=fronius.FroniusWR(fronius_address,fronius_user,fronius_password)
        
        self.pvsettings=config['pvinstallations']
        self.fc_solar = forecastsolar.ForecastSolar(self.pvsettings)
        
        self.load_profile=config['load_profile']
        self.fc_consumption = forecastconsumption.ForecastConsumption(self.load_profile)
        
        self.config=config['battery_control']
        
    def __del__(self):
        del self.inverter
            
    def load_config(self, configfile):
        
        if not os.path.isfile(configfile):
            raise RuntimeError('Configfile {configfile} not found')
        
        with open(configfile, 'r') as f:
            config_str=f.read()
            
        config=yaml.safe_load(config_str)

        if config['utility']['type'] == 'tibber':
            pass
        else: 
            raise RuntimeError('Unkonwn Utility')

        if config['inverter']['type']=='fronius_gen24':
            pass
        else:
            raise RuntimeError('Unkown inverter')

        self.config=config

        if config['pvinstallations']:
           pass
        else:
            raise RuntimeError('No PV Installation found')
        
        if not os.path.isfile(config['load_profile']):
            raise RuntimeError('Load Profile file not found')

    def run(self):
        price_dict = self.tibber.get_prices()
        
        production_forecast = self.fc_solar.get_forecast()
        fc_period = min(max(price_dict.keys()), max( production_forecast.keys()))
        consumption_forecast = self.fc_consumption.get_forecast(fc_period+1)

        net_consumption = np.zeros(fc_period+1)
        production=np.zeros(fc_period+1)
        consumption=np.zeros(fc_period+1)
        prices=np.zeros(fc_period+1)

        for h in range(fc_period+1):
            production[h]=production_forecast[h]
            consumption[h]=consumption_forecast[h]
            prices[h]=price_dict[h]
        
        net_consumption=consumption-production

        logger.debug(f'[BatCTRL] Production FCST {production}')
        logger.debug(f'[BatCTRL] Consumption FCST {consumption}')
        logger.debug(f'[BatCTRL] Net Consumption FCST {net_consumption}')
        logger.debug(f'[BatCTRL] prices {prices}')
        # negative = charging or feed in
        # positive = dis-charging or grid consumption

        #correction for time that has already passed since the start of the current hour
        net_consumption[0]*=1-datetime.datetime.now().minute/60
        min_SOC, max_SOC,allow_grid_charging,grid_power =self.get_wr_parameters(self.inverter,net_consumption,price_dict)
        
        if not self.is_simulation:
            self.inverter.set_wr_parameters(min_SOC, max_SOC,allow_grid_charging,grid_power)
        else:
            logger.info(f'[Batcontrol] SIMULATION inverter parameters {inverter_params}')
    #%%
    def get_wr_parameters(self, wr:fronius.FroniusWR, net_consumption:np.ndarray, prices:dict):
        #ensure availability of data
        max_hour=min(len(net_consumption),len(prices))
        
        #current price as reference
        current_price=prices[0]
        
        #find first hour with price< current price
        for h in range(1,max_hour):
            future_price=prices[h]
            if future_price <=current_price:
                max_hour=h
                break
        if self.is_discharge_allowed(wr, net_consumption[:max_hour], prices):
            logger.debug(f'[BatCTRL] Evaluated until hour now+{max_hour}')
            logger.debug(f'[BatCTRL] Mode: Allow Discharging' )
            allow_grid_charging=False
            min_SOC=wr.min_soc
            max_SOC=wr.max_soc
            grid_power=0
        else: #discharge not allowed
            charging_limit=self.config['max_charging_from_grid_limit']
            required_recharge_energy=self.get_required_required_recharge_energy(wr, net_consumption[:max_hour], prices)
            is_charging_possible=wr.get_SOC()<(wr.max_soc*charging_limit)
            
            logger.debug('[BatCTRL] Discharging is NOT allowed')
            logger.debug(f'[BatCTRL] Charging allowed: {is_charging_possible}')
            logger.debug(f'[BatCTRL] Enery required: {required_recharge_energy}' )
            #charge if battery capacity available and more stored energy is required
            if is_charging_possible and required_recharge_energy>0:
                allow_grid_charging=True
                remaining_time=(60-datetime.datetime.now().minute)/60
                charge_rate=required_recharge_energy/remaining_time
                charge_rate=min(charge_rate,wr.max_charge_rate)
                grid_power=net_consumption+charge_rate
                max_SOC=wr.max_soc*charging_limit #reserve some capacity for unexpected production
                min_SOC=max_SOC #high min soc to avoid solar energy flowing into the grid
                logger.debug(f'[BatCTRL] Mode: Charging from Grid. Charge rate/ grid_power {charge_rate} / {grid_power} W' )
            else: #keep current charge level. recharge if solar surplus available
                max_SOC=wr.max_soc
                allow_grid_charging=False
                grid_power=0
                min_SOC=max_SOC #high min soc to avoid solar energy flowing into the grid
                logger.debug(f'[BatCTRL] Mode: Avoid discharge' )
                    
        return min_SOC, max_SOC,allow_grid_charging,grid_power
                
    #%%
    def get_required_required_recharge_energy(self,wr:fronius.FroniusWR, net_consumption:list, prices:dict):
        current_price=prices[0]
        max_hour=len(net_consumption)
        consumption=np.array(net_consumption)
        consumption[consumption<0]=0
        
        production=-np.array(net_consumption)
        production[production<0]=0
        min_price_difference=self.config['min_price_difference']
        
        #evaluation period until price is first time lower then current price
        for h in range(1,max_hour):
            future_price=prices[max_hour]
            if future_price<=current_price:
                max_hour=h
        
        #get high price hours
        high_price_hours=[]
        for h in range(max_hour):
            future_price=prices[h]
            if future_price > current_price+min_price_difference:
                high_price_hours.append(h)
        
        #start with latest hour
        high_price_hours.sort()
        high_price_hours.reverse()
        required_recharge_energy=0
        for high_price_hour in high_price_hours:
            energy_to_shift=consumption[high_price_hour]
            
            #correct energy to shift with potential production
            #start with latest hour
            for hour in list(range(high_price_hour))[::-1]:
                if production[hour]==0:
                    continue
                if production[hour]>=energy_to_shift:
                    production[hour]-=energy_to_shift
                    energy_to_shift=0
                else: #
                    energy_to_shift-=production[hour]
                    production[hour]
            #add_remaining energy to shift to recharge amount
            required_recharge_energy+=energy_to_shift
        
        
        free_capacity=wr.get_free_capacity()
        recharge_energy=min(free_capacity,recharge_energy)
        
        return recharge_energy
            
#%%

    def is_discharge_allowed(self, wr:fronius.FroniusWR, net_consumption:np.ndarray, prices:dict):
        #always allow discharging when battery is >90% maxsoc
        allow_discharge_limit=self.config['always_allow_discharge_limit']
        if wr.get_SOC() >wr.max_soc*allow_discharge_limit:
            return True
        
        current_price=prices[0]
        min_price_difference=self.config['min_price_difference']
        max_hour=len(net_consumption)
        #relevant time range : until next recharge possibility
        for h in range(1,max_hour):
            future_price=prices[h]
            if future_price <=current_price-min_price_difference:
                max_hour=h
                break
        
        #distribute remaining energy
        consumption=np.array(net_consumption)
        consumption[consumption<0]=0
        
        production=-np.array(net_consumption)
        production[production<0]=0
        
        #get hours with higher price
        higher_price_hours=[]
        for h in range(max_hour):
            future_price=prices[h]
            if future_price > current_price: #!!! different formula compared to detect relevant hours
                higher_price_hours.append(h)    
        
        higher_price_hours.sort()
        higher_price_hours.reverse()
        
        reserved_storage=0
        for higher_price_hour in higher_price_hours:
            if consumption[higher_price_hour]==0:
                continue
            required_energy=consumption[higher_price_hour]
                
            #correct reserved_storage with potential production
            #start with latest hour
            for hour in list(range(higher_price_hour))[::-1]:
                if production[hour]==0:
                    continue
                if production[hour]>=required_energy:
                    production[hour]-=required_energy
                    required_energy=0
                else: #
                    required_energy-=production[hour]
                    production[hour]=0
            #add_remaining required_energy to reserved_storage
            reserved_storage+=required_energy
        
        stored_energy=wr.get_stored_energy()
        
        if (stored_energy>reserved_storage):
            #allow discharging
            return True
        else:
            #forbid discharging
            return False
                

if __name__ == '__main__':
    bc=Batcontrol('config.yaml')
    try:
        while(1):
            bc.run()
            time.sleep(60)
    except KeyboardInterrupt:
        del bc
        