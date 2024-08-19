class Inverter(object):
    def __new__(cls, config:dict):
        if config['type'].lower() == 'fronius_gen24':
            from .fronius import FroniusWR
            return FroniusWR(config['address'], config['user'], config['password'], config['max_charge_rate'])
        elif config['type'].lower() == 'testdriver':
            from .testdriver import Testdriver
            return Testdriver(config['max_charge_rate'])
        else:
            raise RuntimeError(f'[Inverter] Unkown inverter type {config["type"]}')