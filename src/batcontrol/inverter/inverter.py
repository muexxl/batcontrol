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
                'max_pv_charge_rate': config['max_pv_charge_rate'],
                'fronius_inverter_id': config.get('fronius_inverter_id', 1),
                'fronius_controller_id': config.get('fronius_controller_id', 0)
            }
            inverter=FroniusWR(iv_config)
        elif config['type'].lower() == 'dummy':
            from .dummy import Dummy
            iv_config = {
                'max_grid_charge_rate': config['max_grid_charge_rate']
            }
            inverter=Dummy(iv_config)
        elif config['type'].lower() == 'mqtt':
            from .mqtt_inverter import MqttInverter
            iv_config = {
                'base_topic': config.get('base_topic', 'default'),
                'capacity': config['capacity'],
                'min_soc': config.get('min_soc', 5),
                'max_soc': config.get('max_soc', 100),
                'max_grid_charge_rate': config['max_grid_charge_rate']
            }
            inverter=MqttInverter(iv_config)
        else:
            raise RuntimeError(f'[Inverter] Unkown inverter type {config["type"]}')

        inverter.inverter_num = Inverter.num_inverters
        Inverter.num_inverters += 1
        return inverter
