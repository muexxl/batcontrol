
# API to publish data from batcontrol to MQTT for further processing+visualization
#
#  base_topic : string  # topic to publish to
#            /status  : online/offline  # is batcontrol running?
#            /mode    : -1 = charge from grid , 0 = avoid discharge , 10 = discharge allowed 
#
#            /SOC : float  # State of Charge in %
#
#            /max_charging_from_grid_limit : float  # Charge limit in %
#            /always_allow_discharge_limit : float  # Discharge limit in 0.0-1.0 (%)
#
#            /discharge_limit : float  # Discharge limit in W
#            /charge_rate : float  # Charge rate in W
#            /stored_energy : float  # Energy stored in battery in Wh
#            /reserved_energy : float  # Energy reserved for discharge in Wh
#
#            /min_price_difference : float  # Minimum price difference in EUR
#
#          /max_capacity : float  # Maximum capacity of battery in Wh
#
#    Following statistical arrays as JSON Arrays
#            /FCST/production        # Forecasted production in W
#            /FCST/consumption       # Forecasted consumption in W
#            /FCST/prices            # Forecasted price in EUR
#            /FCST/net_consumption   # Forecasted net consumption in W
#


import json
import logging
import paho.mqtt.client as mqtt
import numpy as np
import time

logger = logging.getLogger('__main__')
logger.info(f'[MQTT] loading module ')

mqtt_api = None

## Callbacks go through 
def on_connect( client, userdata, flags, rc ):
    logger.info(f'[MQTT] Connected with result code {rc}')
    # Make public, that we are running.
    client.publish(mqtt_api.base_topic + '/status', 'online', retain=True)


class MQTT_API(object):
    def __init__(self, config:dict):
        self.config=config
        self.base_topic = config['topic']

        self.client = mqtt.Client()
        self.client.enable_logger(logger)
        if 'username' in config and 'password' in config:
            self.client.username_pw_set(config['username'], config['password'])
        
        self.client.will_set(self.base_topic + '/status', 'offline', retain=True)
        global mqtt_api
        mqtt_api = self

        # TLS , not tested yet
        if config['tls'] == True:
            self.client.tls_set(config['tls']['ca_certs'], config['tls']['certfile'], config['tls']['keyfile'], cert_reqs=config['tls']['cert_reqs'], tls_version=config['tls']['tls_version'], ciphers=config['tls']['ciphers'])

        self.client.on_connect = on_connect
        self.client.loop_start()

        self.client.connect(config['broker'], config['port'], 60)

        return 
    
    def wait_ready(self) -> bool:
        retry = 30
        # Check if we are connected and wait for it
        while self.client.is_connected() == False:
            retry -= 1
            if retry == 0:
                logger.error(f'[MQTT] Could not connect to MQTT Broker')
                return False
            logger.info(f'[MQTT] Waiting for connection')
            time.sleep(1)

        return True

    
    def publish_mode(self, mode:int) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/mode', mode)
        return

    def publish_charge_rate(self, rate:float) -> None:
        if self.client.is_connected() == True:        
            self.client.publish(self.base_topic + '/charge_rate', rate)
        return            
    
    def publish_production(self, production:np.ndarray, timestamp:float) -> None:
        if self.client.is_connected() == True:
            #self.client.publish(self.base_topic + '/FCST/production', json.dumps(production.tolist()))

            self.client.publish(self.base_topic + '/FCST/production', json.dumps(self._create_forecast(production, timestamp)))
        return            

    def _create_forecast(self, forecast:np.ndarray, timestamp:float) -> dict:
        # Take timestamp and reduce it to the first second of the hour
        now = timestamp - (timestamp % 3600)
        
        list = []
        for h in range(0, len(forecast)):
            # nächste stunde nach now
            list.append ({ 'time_start' :now + h * 3600 , 'value' :   forecast[h] , 'time_end' : now -1  + ( h+1) *3600  })

        data = { 'data' : list }
        return data
    

    def publish_consumption(self, consumption:np.ndarray, timestamp:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/FCST/consumption', json.dumps(self._create_forecast(consumption,timestamp)))
        return            

    def publish_prices(self, price:np.ndarray ,timestamp:float) -> None:  
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/FCST/prices', json.dumps(self._create_forecast(price,timestamp)))
        return            

    def publish_net_consumption(self, net_consumption:np.ndarray, timestamp:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/FCST/net_consumption', json.dumps(self._create_forecast(net_consumption,timestamp)))
        return
    
    def publish_SOC(self, soc:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/SOC', soc)
        return
    
    def publish_stored_energy(self, stored_energy:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/stored_energy', stored_energy)
        return
    
    def publish_reserved_energy(self, reserved_energy:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/reserved_energy', str(reserved_energy))
        return
    
    def publish_discharge_limit(self, discharge_limit:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/discharge_limit', str(discharge_limit))
        return
    
    def publish_always_allow_discharge_limit(self, allow_discharge_limit:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/always_allow_discharge_limit', allow_discharge_limit * 100)
        return
    
    def publish_max_charging_from_grid_limit(self, charge_limit:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/max_charging_from_grid_limit', charge_limit * 100)
        return
    
    def publish_min_price_difference(self, min_price_differences:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/min_price_differences', min_price_differences)
        return
    
    def publish_max_capacity(self, max_capacity:float) -> None:
        if self.client.is_connected() == True:
            self.client.publish(self.base_topic + '/max_capacity', max_capacity)
        return