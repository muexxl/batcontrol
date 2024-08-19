import logging
from .baseclass import InverterBaseclass

logger = logging.getLogger('__main__')
logger.info(f'[Fronius] loading module ')

#from .fronius import InverterBaseclass

class Testdriver(InverterBaseclass):
    def __init__(self, max_charge_rate:float):
        self.max_charge_rate=max_charge_rate
        self.stored_energy=2000
        self.max_capacity=5000
        self.SOC=99.0
        self.mode='allow_discharge'
        
    def set_mode_force_charge(self):
        self.mode='force_charge'
        
    def set_mode_allow_discharge(self):
        self.mode='allow_discharge'
        
    def set_mode_avoid_discharge(self):
        self.mode='avoid_discharge'
        
    def get_stored_energy(self):
        return self.stored_energy
        
    def get_free_capacity(self):
        return self.max_capacity-self.stored_energy
        
    def get_max_capacity(self):
        return self.max_capacity
        
    def get_SOC(self):
        return self.SOC