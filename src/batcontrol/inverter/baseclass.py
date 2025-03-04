""" Parent Class for implementing common functions for all inverters """
from .inverter_interface import InverterInterface

class InverterBaseclass(InverterInterface):
    def __init__(self, config):
        self.min_soc = -1
        self.max_soc = -1
        self.mqtt_api = None
        self.capacity = -1
        self.inverter_num = 0

    def get_capacity(self) -> float:
        """ Dummy implementation """
        raise RuntimeWarning("get_capacity not implemented!")

    def get_SOC(self) -> float:   # pylint: disable=invalid-name
        """ Dummy implementation """
        raise RuntimeWarning("get_capacity not implemented!")

    def get_designed_capacity(self) -> float:
        """ Returns the designed maximum capacity of the battery in kWh,
            which does not include MIN_SOC , MAX_SOC or other restrictions.
        """
        return self.get_capacity()

    def get_stored_energy(self) -> float:
        """ Returns the stored energy in the battery in kWh """
        current_soc = self.get_SOC()
        capa = self.get_capacity()
        energy = current_soc/100*capa
        if energy < 0:
            return 0
        return energy

    def get_stored_usable_energy(self) -> float:
        """ Returns the stored energy in the battery in kWh which can be used .
            It reduces the amount by the minimum SOC.
        """
        current_soc = self.get_SOC()
        capa = self.get_capacity()
        energy = (current_soc-self.min_soc)/100*capa
        if energy < 0:
            return 0
        return energy

    def get_usable_capacity(self) -> float:
        """ Returns Capacity which can be used from Battery.
            This value is reduced by MIN_SOC & MAX_SOC limitations.
        """
        usable_capa = (self.max_soc-self.min_soc)/100*self.get_capacity()
        return usable_capa

    def get_max_capacity(self) -> float:
        """ Returns Capacity reduced by MAX_SOC """
        return self.max_soc/100*self.get_capacity()

    def get_free_capacity(self) -> float:
        """ Return Capacity Wh to be chargeable
            this value is reduced by MAX_SOC.
        """
        current_soc = self.get_SOC()
        capa = self.get_capacity()
        free_capa = (self.max_soc-current_soc)/100*capa
        return free_capa

    # Used to implement the mqtt basic topic.
    def __get_mqtt_topic(self) -> str:
        return f'inverters/{self.inverter_num}/'

    def refresh_api_values(self):
        if self.mqtt_api:
            self.mqtt_api.generic_publish(self.__get_mqtt_topic() + 'SOC', self.get_SOC())
            self.mqtt_api.generic_publish(self.__get_mqtt_topic() + 'mode', self.mode)
            self.mqtt_api.generic_publish(self.__get_mqtt_topic() + 'stored_energy', self.get_stored_energy())
            self.mqtt_api.generic_publish(self.__get_mqtt_topic() + 'stored_usable_energy', self.get_stored_usable_energy())
            self.mqtt_api.generic_publish(self.__get_mqtt_topic() + 'free_capacity', self.get_free_capacity())
            self.mqtt_api.generic_publish(self.__get_mqtt_topic() + 'max_capacity', self.get_max_capacity())

    def shutdown(self):
        pass
