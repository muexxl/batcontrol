""" Factory for inverter providers """

from .inverter_interface import InverterInterface



class Inverter:
    """ Factory for inverter providers """
    # Instances of the inverter classes are created here
    num_inverters = 0
    @staticmethod
    def create_inverter(config: dict) -> InverterInterface:
        """ Select and configure an inverter based on the given configuration """
        # renaming of parameters max_charge_rate -> max_grid_charge_rate
        if not 'max_grid_charge_rate' in config.keys():
            config['max_grid_charge_rate'] = config['max_charge_rate']

        # introducing parameter max_pv_charge_rate. Assign default value here,
        # in case there is no value defined in the config file to avoid a KeyError
        if not 'max_pv_charge_rate' in config.keys():
            config['max_pv_charge_rate'] = 0

        inverter = None

        if config['type'].lower() == 'fronius_gen24':
            from .fronius import FroniusWR

            iv_config = {
                'address': config['address'],
                'user': config['user'],
                'password': config['password'],
                'max_grid_charge_rate': config['max_grid_charge_rate'],
                'max_pv_charge_rate': config['max_pv_charge_rate']
            }
            inverter=FroniusWR(iv_config)
        elif config['type'].lower() == 'testdriver':
            from .testdriver import Testdriver
            iv_config = {
                'max_grid_charge_rate': config['max_grid_charge_rate']
            }
            inverter=Testdriver(iv_config)
        else:
            raise RuntimeError(f'[Inverter] Unkown inverter type {config["type"]}')

        inverter.inverter_num = Inverter.num_inverters
        Inverter.num_inverters += 1
        return inverter
