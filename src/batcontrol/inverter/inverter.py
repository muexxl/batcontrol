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
        elif config['type'].lower() == 'dummy':
            from .dummy import Dummy
            iv_config = {
                'max_grid_charge_rate': config['max_grid_charge_rate']
            }
            inverter=Dummy(iv_config)
        elif config['type'].lower() == 'mqtt':
            from .mqtt_inverter import MqttInverter
            iv_config = {
                'mqtt_broker': config['mqtt_broker'],
                'mqtt_port': config['mqtt_port'],
                'mqtt_user': config.get('mqtt_user'),
                'mqtt_password': config.get('mqtt_password'),
                'base_topic': config['base_topic'],
                'capacity': config['capacity'],
                'min_soc': config.get('min_soc', 10),
                'max_soc': config.get('max_soc', 95),
                'max_grid_charge_rate': config['max_grid_charge_rate']
            }
            inverter=MqttInverter(iv_config)
        else:
            raise RuntimeError(f'[Inverter] Unkown inverter type {config["type"]}')

        inverter.inverter_num = Inverter.num_inverters
        Inverter.num_inverters += 1
        return inverter
