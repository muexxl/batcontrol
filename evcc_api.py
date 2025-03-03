"""
This module provides the EvccApi class for interacting with an
evcc (Electric Vehicle Charging Controller) via MQTT.
"""
import time
import re
import logging
import paho.mqtt.client as mqtt

logger = logging.getLogger('__main__').getChild("evcc")
logger.info('[evcc] loading module')


class EvccApi():
    """
    A class to interact with the evcc (Electric Vehicle Charging Controller) via MQTT.

    Attributes:
        config (dict): Configuration dictionary containing MQTT broker details, topics.
        evcc_is_online (bool): Internal state indicating if evcc is online.
        evcc_is_charging (bool): Internal state indicating if evcc is charging.
        evcc_batter_halt_soc (int): BufferSOC value from evcc.
        battery_halt_soc_float (float): BufferSOC value as float.
        block_function (function): Function to be called to block/unblock Battery.
        set_always_allow_discharge_limit_function (function): Function to set the discharge limit.
        get_always_allow_discharge_limit_function (function): Function to get the discharge limit.
        evcc_loadpoint_status (dict): Internal state to store the loadpoint status.
        topic_status (str): MQTT topic for evcc status messages.
        topic_loadpoint (str): MQTT topic for evcc loadpoint messages.
        topic_battery_halt_soc (str): MQTT topic for evcc battery SOC threshold.
        client (mqtt.Client): MQTT client instance.
        align_battery_load_thresshold (bool): If set, use evcc/site/bufferSoc as
                                              discharge_allow_threshold while charging.
        old_allow_discharge_limit (int): Old discharge_allow_threshold value.

    Methods:
        __init__(config: dict):
            Initializes the EvccApi instance with the given configuration.

        wait_ready() -> bool:
            Waits until the MQTT client is connected to the broker.

        register_block_function(function):
            Registers a function to be called to block/unblock charging.

        register_always_allow_discharge_limit(setter, getter):
            Registers a function to set and get the discharge limit while charging

        register_max_charge_limit(setter, getter):
            Registers a function to set and get the max charge limit while charging

        set_evcc_online(online: bool):
            Sets the evcc online status and handles state changes.

        set_evcc_charging(charging: bool):
            Sets the evcc charging status and handles state changes.

        handle_status_messages(message):
            Handles incoming status messages from the MQTT broker.

        handle_charging_message(message):
            Handles incoming charging messages from the MQTT broker.

        handle_battery_halt_soc(message):
            Handles incoming evcc config messages from the MQTT broker.

        _handle_message(client, userdata, message):
            Internal callback function to handle incoming MQTT messages.
    """

    def __init__(self, config: dict):
        self.config = config

        # internal state
        self.evcc_is_online = False
        self.evcc_is_charging = False

        self.evcc_loadpoint_status = {}

        self.block_function = None
        self.set_always_allow_discharge_limit_function = None
        self.get_always_allow_discharge_limit_function = None
        self.set_max_charge_limit_function = None
        self.get_max_charge_limit_function = None

        self.topic_status = config['status_topic']
        self.list_topics_loadpoint = []
        self.topic_battery_halt_soc = config.get(
            'battery_halt_topic', None)
        self.evcc_battery_halt_soc = None
        self.battery_halt_soc_float = None
        self.old_allow_discharge_limit = None
        self.old_max_charge_limit = None

        if isinstance(config['loadpoint_topic'], str):
            self.list_topics_loadpoint.append(config['loadpoint_topic'])
        elif isinstance(config['loadpoint_topic'], list):
            self.list_topics_loadpoint = config['loadpoint_topic']
        else:
            logger.error('[evcc] Invalid loadpoint_topic type')

        self.client = mqtt.Client(clean_session=True)

        if 'logger' in config and config['logger'] is True:
            self.client.enable_logger(logger)

        if 'username' in config and 'password' in config:
            self.client.username_pw_set(config['username'], config['password'])

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

        # Register callback functions, survives reconnects
        self.client.message_callback_add(
            self.topic_status, self._handle_message)
        if self.topic_battery_halt_soc is not None:
            logger.info('[evcc] Enabling battery threshold management.')
            self.client.message_callback_add(
                self.topic_battery_halt_soc, self._handle_message)
        for topic in self.list_topics_loadpoint:
            self.__store_loadpoint_status(topic, False)
            self.client.message_callback_add(topic, self._handle_message)

        self.client.on_connect = self.on_connect

    def start(self):
        """ Start MQTT connection after all init is completed"""
        self.client.loop_start()
        self.client.connect(self.config['broker'], self.config['port'], 60)
        self.wait_ready()

    def shutdown(self):
        """ Shutdown the evcc mqtt client """
        self.client.unsubscribe(self.topic_status)
        if self.topic_battery_halt_soc is not None:
            self.client.unsubscribe(self.topic_battery_halt_soc)
        for topic in self.list_topics_loadpoint:
            self.client.unsubscribe(topic)
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, rc):  # pylint: disable=unused-argument
        """ Callback function for MQTT on_connect """
        logger.info('[evcc] Connected to MQTT Broker with result code %s', rc)
        # Subscribe to status and loadpoint(s)
        self.client.subscribe(self.topic_status, qos=1)
        if self.topic_battery_halt_soc is not None:
            self.client.subscribe(self.topic_battery_halt_soc, qos=1)
        for topic in self.list_topics_loadpoint:
            logger.info('[evcc] Subscribing to %s', topic)
            self.client.subscribe(topic)

    def wait_ready(self) -> bool:
        """ Wait until the MQTT client is connected to the broker """
        retry = 30
        # Check if we are connected and wait for it
        while self.client.is_connected() is False:
            retry -= 1
            if retry == 0:
                logger.error('[evcc] Could not connect to MQTT Broker')
                return False
            logger.info('[evcc] Waiting for connection')
            time.sleep(1)
        return True

    def register_block_function(self, function):
        """ Register a function to be called to block/unblock battery while charging """
        self.block_function = function

    def register_always_allow_discharge_limit(self, setter, getter):
        """ Register a function to set and get the discharge limit while charging """
        self.set_always_allow_discharge_limit_function = setter
        self.get_always_allow_discharge_limit_function = getter

    def register_max_charge_limit(self, setter, getter):
        """ Register a function to set and get the max charge limit while charging """
        self.set_max_charge_limit_function = setter
        self.get_max_charge_limit_function = getter

    def __save_old_allow_discharge_limit(self):
        """ Save old limit, if not already set."""
        if self.old_allow_discharge_limit is None:
            self.old_allow_discharge_limit = self.get_always_allow_discharge_limit_function()
        if self.old_max_charge_limit is None:
            self.old_max_charge_limit = self.get_max_charge_limit_function()
            if self.old_max_charge_limit < self.battery_halt_soc_float:
                # Only store if the old value is higher than the new battery_hold one,
                # which will may be altered by batcontrol to a lower value.
                self.old_max_charge_limit = None

    def __restore_old_allow_discharge_limit(self):
        """ Restore old limit, if set and set to None """
        if not self.old_allow_discharge_limit is None:
            logger.info("[evcc] Restoring allow_discharge_limit %.2f",
                        self.old_allow_discharge_limit)
            self.set_always_allow_discharge_limit_function(
                self.old_allow_discharge_limit)
            self.old_allow_discharge_limit = None
        # This value may be changed, too, so we restore it
        if not self.old_max_charge_limit is None:
            logger.info("[evcc] Restoring max_charge_limit %.2f",
                        self.old_max_charge_limit)
            self.set_max_charge_limit_function(self.old_max_charge_limit)
            self.old_max_charge_limit = None

    def set_evcc_discharge_limit_on_batcontrol(self):
        """ Set allow_discharge_limit on batcontrol"""
        if self.evcc_battery_halt_soc is not None:
            logger.info('[evcc] Setting always_allow_discharge_limit to %.2f',
                        self.battery_halt_soc_float)
            self.set_always_allow_discharge_limit_function(
                self.battery_halt_soc_float
            )
        else:
            logger.error('[evcc] No evcc battery hold config value received')

    def set_evcc_online(self, online: bool):
        """ Set the evcc online status and handle state changes.
            If the evcc goes offline while charging, we remove an existing block.
        """
        if self.evcc_is_online != online:
            if online is False:
                logger.error('[evcc] evcc went offline')
                if self.evcc_is_charging is True:
                    # We remove the block, that we set to not end endless in block mode
                    logger.error('[evcc] evcc was charging, remove block')
                    self.evcc_is_charging = False
                    self.block_function(False)
                    self.__restore_old_allow_discharge_limit()
                    self.__reset_loadpoint_status()
            else:
                logger.info('[evcc] evcc is online')
            self.evcc_is_online = online

    def set_evcc_charging(self, charging: bool):
        """ Set the evcc charging status and handle state changes """
        if self.evcc_is_charging != charging:
            if charging is True:
                # We set the block, so we do not discharge the battery
                logger.info('[evcc] evcc is charging, set block')
                self.evcc_is_charging = True
                self.block_function(True)
                if self.topic_battery_halt_soc is not None:
                    self.__save_old_allow_discharge_limit()
                    self.set_evcc_discharge_limit_on_batcontrol()
            else:
                logger.info('[evcc] evcc is not charging, remove block')
                self.evcc_is_charging = False
                self.block_function(False)
                self.__restore_old_allow_discharge_limit()
        self.evcc_is_charging = charging

    def __store_loadpoint_status(self, topic: str, is_charging: bool):
        """ Store the loadpoint status """
        send_info = False
        if topic not in self.evcc_loadpoint_status:
            self.evcc_loadpoint_status[topic] = is_charging
            send_info = True
        if self.evcc_loadpoint_status[topic] != is_charging:
            self.evcc_loadpoint_status[topic] = is_charging
            send_info = True
        # Send info if status changed
        if send_info is True:
            if is_charging is False:
                logger.info('[evcc] Loadpoint %s is not charging.', topic)
            else:
                logger.info('[evcc] Loadpoint %s is charging.', topic)

    def __reset_loadpoint_status(self):
        """ Reset the loadpoint status """
        for topic in self.list_topics_loadpoint:
            self.evcc_loadpoint_status[topic] = False

    def handle_status_messages(self, message):
        """ Handle incoming status messages from the MQTT broker """
        # logger.debug('[evcc] Received status message: %s', message.payload)
        if message.payload == b'online':
            self.set_evcc_online(True)
        elif message.payload == b'offline':
            self.set_evcc_online(False)

    def handle_battery_halt_soc(self, message):
        """ Handling incoming config message, change if needed. """
        if message.payload == b'':
            # Initial Messages from evcc on restart.
            return
        try:
            new_soc = int(message.payload)
            if self.evcc_battery_halt_soc is None or \
               self.evcc_battery_halt_soc != new_soc:
                self.evcc_battery_halt_soc = new_soc
                logger.info('[evcc] New battery_halt value: %s', new_soc)
                self.battery_halt_soc_float = new_soc / 100
                if self.evcc_is_charging is True:
                    self.set_always_allow_discharge_limit_function(
                        self.battery_halt_soc_float)
        except ValueError:
            logger.error('[evcc] Could not convert battery_halt to int')

    def handle_charging_message(self, message):
        """ Handle incoming charging messages from the MQTT broker """
        if message.payload == b'':
            # Initial Messages from evcc on restart.
            return
        if re.match(b'true', message.payload, re.IGNORECASE):
            self.__store_loadpoint_status(message.topic, True)
        elif re.match(b'false', message.payload, re.IGNORECASE):
            self.__store_loadpoint_status(message.topic, False)

        self.evaluate_charging_status()

    def evaluate_charging_status(self):
        """ Go through the loadpoints and check if one is charging """
        for _, is_charging in self.evcc_loadpoint_status.items():
            if is_charging is True:
                self.set_evcc_charging(True)
                return
        self.set_evcc_charging(False)

    def _handle_message(self, client, userdata, message):  # pylint: disable=unused-argument
        """ Message dispatching function """
        # logger.debug('[evcc] Received message on %s', message.topic)
        if message.topic == self.topic_status:
            self.handle_status_messages(message)
        elif self.topic_battery_halt_soc is not None and \
                message.topic == self.topic_battery_halt_soc:
            self.handle_battery_halt_soc(message)
        # Check if message.topic is in self.list_topics_loadpoint
        elif message.topic in self.list_topics_loadpoint:
            self.handle_charging_message(message)
        else:
            logger.warning(
                '[evcc] No callback registered for %s', message.topic)
