import logging
from .baseclass import InverterBaseclass
from .inverter_interface import InverterInterface
from ..mqtt_api import MqttApi

logger = logging.getLogger('__main__')
logger.info('[Testdriver] loading module')

#from .fronius import InverterBaseclass

# Testdriver to simulate a inverter for local testing.
#
# Following values can be set via MQTT:
# - SOC (int): State of charge in percent
#            : <mqtt_topic>/inverters/0/SOC/set


class Testdriver(InverterBaseclass):
    def __init__(self, config):
        super().__init__(config)
        self.max_grid_charge_rate=config['max_grid_charge_rate']
        self.installed_capacity=11000 # in Wh
        self.SOC=69.0 # static simulation SOC in percent
        self.min_soc=8 # in percent
        self.max_soc=100 # in percent
        self.mode='allow_discharge'
        self.mqtt_api = None

    def set_mode_force_charge(self,chargerate=500):
        self.mode='force_charge'

    def set_mode_allow_discharge(self):
        self.mode='allow_discharge'

    def set_mode_avoid_discharge(self):
        self.mode='avoid_discharge'

    def get_capacity(self):
        return self.installed_capacity

    def get_SOC(self):
        return self.SOC

    def api_set_SOC(self, SOC:int):
        if SOC < 0 or SOC > 100:
            logger.warning(f'[BatCtrl] testdriver API: Invalid SOC {SOC}')
            return
        logger.info(f'[BatCtrl] testdriver API: Setting SOC: {SOC}%')
        self.SOC = SOC

    def activate_mqtt(self, api_mqtt_api):
        self.mqtt_api = api_mqtt_api
        # /set is appended to the topic
        self.mqtt_api.register_set_callback(self.__get_mqtt_topic() + 'SOC', self.api_set_SOC, int)

    def refresh_api_values(self):
        super().refresh_api_values()
        if self.mqtt_api:
            self.mqtt_api.generic_publish(self.__get_mqtt_topic() + 'mode', self.mode)

    def shutdown(self):
        pass

    def __get_mqtt_topic(self) -> str:
        return f'inverters/{self.inverter_num}/'
