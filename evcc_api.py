
"""
This module provides the EvccApi class for interacting with an
evcc (Electric Vehicle Charging Controller) via MQTT.
"""
import time
import re
import logging
import paho.mqtt.client as mqtt

logger = logging.getLogger('__main__')
logger.info('[evcc] loading module')

class EvccApi():
    """
    A class to interact with the evcc (Electric Vehicle Charging Controller) via MQTT.

    Attributes:
        config (dict): Configuration dictionary containing MQTT broker details, topics.
        evcc_is_online (bool): Internal state indicating if evcc is online.
        evcc_is_charging (bool): Internal state indicating if evcc is charging.
        block_function (function): Function to be called to block/unblock Battery.
        topic_status (str): MQTT topic for evcc status messages.
        topic_loadpoint (str): MQTT topic for evcc loadpoint messages.
        client (mqtt.Client): MQTT client instance.

    Methods:
        __init__(config: dict):
            Initializes the EvccApi instance with the given configuration.

        wait_ready() -> bool:
            Waits until the MQTT client is connected to the broker.

        register_block_function(function):
            Registers a function to be called to block/unblock charging.

        set_evcc_online(online: bool):
            Sets the evcc online status and handles state changes.

        set_evcc_charging(charging: bool):
            Sets the evcc charging status and handles state changes.

        handle_status_messages(message):
            Handles incoming status messages from the MQTT broker.

        handle_charging_message(message):
            Handles incoming charging messages from the MQTT broker.

        _handle_message(client, userdata, message):
            Internal callback function to handle incoming MQTT messages.
    """
    def __init__(self, config:dict):
        self.config=config

        # internal state
        self.evcc_is_online = False
        self.evcc_is_charging = False

        self.evcc_loadpoint_status = {}

        self.block_function = None

        self.topic_status = config['status_topic']
        self.list_topics_loadpoint = []

        if isinstance(config['loadpoint_topic'], str):
            self.list_topics_loadpoint.append(config['loadpoint_topic'])
        elif isinstance(config['loadpoint_topic'], list):
            self.list_topics_loadpoint = config['loadpoint_topic']
        else:
            logger.error('[evcc] Invalid loadpoint_topic type')

        self.client = mqtt.Client()
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

        self.client.loop_start()
        self.client.connect(config['broker'], config['port'], 60)
        self.client.on_connect = self.on_connect

        self.wait_ready()
        # Register callback functions, survives reconnects
        self.client.message_callback_add(self.topic_status, self._handle_message)
        for topic in self.list_topics_loadpoint:
            self.__store_loadpoint_status(topic, False)
            self.client.message_callback_add(topic, self._handle_message)

    def on_connect(self, client, userdata, flags, rc): # pylint: disable=unused-argument
        """ Callback function for MQTT on_connect """
        logger.info('[evcc] Connected to MQTT Broker with result code %s', rc)
        # Subscribe to status and loadpoint(s)
        self.client.subscribe(self.topic_status)
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

    def set_evcc_online(self, online:bool):
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
                    self.__reset_loadpoint_status()
            else:
                logger.info('[evcc] evcc is online')
            self.evcc_is_online = online

    def set_evcc_charging(self, charging:bool):
        """ Set the evcc charging status and handle state changes """
        if self.evcc_is_charging != charging:
            if charging is True:
                # We set the block, so we do not discharge the battery
                logger.info('[evcc] evcc is charging, set block')
                self.evcc_is_charging = True
                self.block_function(True)
            else:
                logger.info('[evcc] evcc is not charging, remove block')
                self.evcc_is_charging = False
                self.block_function(False)
        self.evcc_is_charging = charging

    def __store_loadpoint_status(self, topic:str, is_charging:bool):
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
        if message.payload == b'online':
            self.set_evcc_online(True)
        elif message.payload == b'offline':
            self.set_evcc_online(False)

    def handle_charging_message(self, message):
        """ Handle incoming charging messages from the MQTT broker """
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

    def _handle_message(self, client, userdata, message): # pylint: disable=unused-argument
        """ Message dispatching function """
        logger.debug('[evcc] Received message on %s', message.topic)
        if message.topic == self.config['status_topic']:
            self.handle_status_messages(message)
        # Check if message.topic is in self.list_topics_loadpoint
        elif message.topic in self.list_topics_loadpoint:
            self.handle_charging_message(message)
        else:
            logger.warning('[evcc] No callback registered for %s', message.topic)
