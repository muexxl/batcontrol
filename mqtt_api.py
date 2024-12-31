"""
This module provides an API to publish data from batcontrol to MQTT
for further processing and visualization.

The following topics are published:
- /status: online/offline status of batcontrol
- /evaluation_intervall: interval in seconds
- /last_evaluation: timestamp of last evaluation
- /mode: operational mode (-1 = charge from grid, 0 = avoid discharge, 10 = discharge allowed)
- /max_charging_from_grid_limit: charge limit in 0.1-1
- /max_charging_from_grid_limit_percent: charge limit in %
- /always_allow_discharge_limit: always discharge limit in 0.1-1
- /always_allow_discharge_limit_percent: always discharge limit in %
- /always_allow_discharge_limit_capacity: always discharge limit in Wh
- /charge_rate: charge rate in W
- /max_energy_capacity: maximum capacity of battery in Wh
- /stored_energy_capacity: energy stored in battery in Wh
- /stored_usable_energy_capacity: energy stored in battery in Wh and usable (min SOC considered)
- /reserved_energy_capacity: estimated energy reserved for discharge in Wh
- /SOC: state of charge in %
- /min_price_difference : minimum price difference in EUR
- /discharge_blocked        : bool  # Discharge is blocked by other sources

The following statistical arrays are published as JSON arrays:
- /FCST/production: forecasted production in W
- /FCST/consumption: forecasted consumption in W
- /FCST/prices: forecasted price in EUR
- /FCST/net_consumption: forecasted net consumption in W

Implemented Input-API:
- /mode/set: set mode (-1 = charge from grid, 0 = avoid discharge, 10 = discharge allowed)
- /charge_rate/set: set charge rate in W, sets mode to -1
- /always_allow_discharge_limit/set: set always discharge limit in 0.1-1
- /max_charging_from_grid_limit/set: set charge limit in 0-1
- /min_price_difference/set: set minimum price difference in EUR

The module uses the paho-mqtt library for MQTT communication and numpy for handling arrays.
"""
import time
import json
import logging
import paho.mqtt.client as mqtt
import numpy as np

logger = logging.getLogger('__main__')
logger.info('[MQTT] loading module ')

class MqttApi:
    """ MQTT API to publish data from batcontrol to MQTT for further processing+visualization"""
    SET_SUFFIX = '/set'
    def __init__(self, config:dict):
        self.config=config
        self.base_topic = config['topic']

        self.callbacks = {}

        self.client = mqtt.Client()
        if 'logger' in config and config['logger'] is True:
            self.client.enable_logger(logger)

        if 'username' in config and 'password' in config:
            self.client.username_pw_set(config['username'], config['password'])

        self.client.will_set(self.base_topic + '/status', 'offline', retain=True)

        # TLS , not tested yet
        if config['tls'] is True:
            self.client.tls_set(
                config['tls']['ca_certs'],
                config['tls']['certfile'],
                config['tls']['keyfile'],
                cert_reqs=config['tls']['cert_reqs'],
                tls_version=config['tls']['tls_version'],
                ciphers=config['tls']['ciphers']
            )

        self.client.on_connect = self.on_connect
        self.client.loop_start()
        retry_attempts = config.get('retry_attempts', 5)
        retry_delay = config.get('retry_delay', 10)
        while retry_attempts > 0:
            try:
                self.client.connect(config['broker'], config['port'], 60)
                break
            except Exception as e:
                logger.error('[MQTT] Connection failed: %s, retrying[%d]x in [%d] seconds', e, retry_attempts, retry_delay)
                retry_attempts -= 1
                if retry_attempts == 0:
                    logger.error('[MQTT] All retry attempts failed')
                    raise
                logger.info('[MQTT] Retrying connection in %d seconds...', retry_delay)
                time.sleep(retry_delay)

    def on_connect(self, client, userdata, flags, rc):
        """ Callback for MQTT connection to serve /status"""
        logger.info('[MQTT] Connected with result code %s', rc)
        # Make public, that we are running.
        client.publish(self.base_topic + '/status', 'online', retain=True)
        # Handle reconnect case
        for topic in self.callbacks:
            logger.debug('[MQTT] Subscribing topic: %s', topic)
            for topic in self.callbacks:
                client.subscribe(topic)

    def wait_ready(self) -> bool:
        """ Wait for MQTT connection to be ready"""
        retry = 30
        # Check if we are connected and wait for it
        while self.client.is_connected() is False:
            retry -= 1
            if retry == 0:
                logger.error('[MQTT] Could not connect to MQTT Broker')
                return False
            logger.info('[MQTT] Waiting for connection')
            time.sleep(1)

        return True

    def _handle_message(self, client, userdata, message):  # pylint: disable=unused-argument
        """ Handle and dispatch incoming messages"""
        logger.debug('[MQTT] Received message on %s', message.topic)
        if message.topic in self.callbacks:
            try:
                self.callbacks[message.topic]['function'](
                    self.callbacks[message.topic]['convert'](message.payload)
                )
            except Exception as e:
                logger.error('[MQTT] Error in callback %s : %s', message.topic, e)
        else:
            logger.warning('[MQTT] No callback registered for %s', message.topic)

    def register_set_callback(self, topic:str,  callback:callable, convert: callable) -> None:
        """ Generic- register a callback for changing values inside batcontrol via
            MQTT set topics
        """
        topic_string = self.base_topic + "/" + topic + MqttApi.SET_SUFFIX
        logger.debug('[MQTT] Registering callback for %s', topic_string)
                # set api endpoints, generic subscription
        self.callbacks[topic_string] = { 'function' : callback , 'convert' : convert }
        self.client.subscribe(topic_string)
        self.client.message_callback_add(topic_string , self._handle_message)

    def publish_mode(self, mode:int) -> None:
        """ Publish the mode (charge, lock, discharge) to MQTT
            /mode
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/mode', mode)

    def publish_charge_rate(self, rate:float) -> None:
        """ Publish the forced charge rate in W to MQTT
            /charge_rate
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/charge_rate', rate)

    def publish_production(self, production:np.ndarray, timestamp:float) -> None:
        """ Publish the production to MQTT
            /FCST/production
            The value is in W and based of solar forecast API.
            The length is the same as used in internal arrays.
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/FCST/production',
                json.dumps(self._create_forecast(production, timestamp))
            )

    def _create_forecast(self, forecast:np.ndarray, timestamp:float) -> dict:
        """ Create a forecast JSON object
            from a numpy array and a timestamp
        """
        # Take timestamp and reduce it to the first second of the hour
        now = timestamp - (timestamp % 3600)

        data_list = []
        for h, value in enumerate(forecast):
            # next hour after now
            data_list.append(
            {
                'time_start': now + h * 3600,
                'value': value,
                'time_end': now - h + (h + 1) * 3600
            }
            )

        data = { 'data' : data_list }
        return data


    def publish_consumption(self, consumption:np.ndarray, timestamp:float) -> None:
        """ Publish the consumption to MQTT
            /FCST/consumption
            The value is in W and based of load profile and multiplied with
                personal yearly consumption.
            The length is the same as used in internal arrays.
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/FCST/consumption',
                json.dumps(self._create_forecast(consumption,timestamp))
            )

    def publish_prices(self, price:np.ndarray ,timestamp:float) -> None:
        """ Publish the prices to MQTT
            /FCST/prices
            The length is the same as used in internal arrays.
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/FCST/prices',
                json.dumps(self._create_forecast(price,timestamp))
            )

    def publish_net_consumption(self, net_consumption:np.ndarray, timestamp:float) -> None:
        """ Publish the net consumption in W to MQTT
            /FCST/net_consumption
            The length is the same as used in internal arrays.
            This is the difference between production and consumption.
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/FCST/net_consumption',
                json.dumps(self._create_forecast(net_consumption,timestamp))
            )

    def publish_SOC(self, soc:float) -> None:       # pylint: disable=invalid-name
        """ Publish the state of charge in % to MQTT
            /SOC
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/SOC', f'{int(soc):03}')

    def publish_stored_energy_capacity(self, stored_energy:float) -> None:
        """ Publish the stored energy capacity in Wh to MQTT
            /stored_energy_capacity
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/stored_energy_capacity', f'{stored_energy:.1f}')

    def publish_stored_usable_energy_capacity(self, stored_energy:float) -> None:
        """ Publish the stored usable energy capacity in Wh to MQTT
            /stored_usable_energy_capacity
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/stored_usable_energy_capacity', f'{stored_energy:.1f}')

    def publish_reserved_energy_capacity(self, reserved_energy:float) -> None:
        """ Publish the reserved energy capacity in Wh to MQTT
            /reserved_energy_capacity
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/reserved_energy_capacity',
                f'{reserved_energy:.1f}'
            )

    def publish_always_allow_discharge_limit_capacity(self, discharge_limit:float) -> None:
        """ Publish the always discharge limit in Wh to MQTT
            /always_allow_discharge_limit_capacity
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/always_allow_discharge_limit_capacity',
                f'{discharge_limit:.1f}'
            )

    def publish_always_allow_discharge_limit(self, allow_discharge_limit:float) -> None:
        """ Publish the always discharge limit to MQTT
            /always_allow_discharge_limit as digit
            /always_allow_discharge_limit_percent
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/always_allow_discharge_limit',
                f'{allow_discharge_limit:.2f}'
            )
            self.client.publish(
                self.base_topic + '/always_allow_discharge_limit_percent',
                f'{allow_discharge_limit * 100:.0f}'
            )

    def publish_max_charging_from_grid_limit(self, charge_limit:float) -> None:
        """ Publish the maximum charging limit to MQTT
            /max_charging_from_grid_limit_percent
            /max_charging_from_grid_limit   as digit.
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/max_charging_from_grid_limit_percent',
                f'{charge_limit * 100:.0f}'
            )
            self.client.publish(
                self.base_topic + '/max_charging_from_grid_limit',
                f'{charge_limit:.2f}'
            )

    def publish_min_price_difference(self, min_price_difference:float) -> None:
        """ Publish the minimum price difference to MQTT found in config
            /min_price_difference
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/min_price_difference',
                f'{min_price_difference:.3f}'
            )

    def publish_max_energy_capacity(self, max_capacity:float) -> None:
        """ Publish the maximum energy capacity to MQTT
            /max_energy_capacity
        """
        if self.client.is_connected():
            self.client.publish(
                self.base_topic + '/max_energy_capacity',
                f'{max_capacity:.1f}'
            )

    def publish_evaluation_intervall(self, intervall:int) -> None:
        """ Publish the evaluation intervall to MQTT
            /evaluation_intervall
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/evaluation_intervall', f'{intervall:.0f}')

    def publish_last_evaluation_time(self, timestamp:float) -> None:
        """ Publish the last evaluation timestamp to MQTT
            This is the time when the last evaluation was started.
            /last_evaluation
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/last_evaluation', f'{timestamp:.0f}')

    def publish_discharge_blocked(self, discharge_blocked:bool) -> None:
        """ Publish the discharge blocked status to MQTT
            /discharge_blocked
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/discharge_blocked', str(discharge_blocked))

    # For depended APIs like the Fronius Inverter classes, which is not directly batcontrol.
    def generic_publish(self, topic:str, value:str) -> None:
        """ Publish a generic value to a topic
            For depended APIs like the Fronius Inverter classes, which is not directly batcontrol.
        """
        if self.client.is_connected():
            self.client.publish(self.base_topic + '/' + topic, value)
