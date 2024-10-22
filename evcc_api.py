import logging
import paho.mqtt.client as mqtt
import time
import re


logger = logging.getLogger('__main__')
logger.info(f'[EVCC] loading module ')

evcc_mqtt_api = None

class EVCC_API(object):
    def __init__(self, config:dict):
        self.config=config

        # internal state
        self.evcc_is_online = False
        self.evcc_is_charging = False

        self.block_function = None

        self.topic_status = config['status_topic']
        self.topic_loadpoint = config['loadpoint_topic']

        self.client = mqtt.Client()
        if 'logger' in config and config['logger'] == True:
            self.client.enable_logger(logger)
        
        if 'username' in config and 'password' in config:
            self.client.username_pw_set(config['username'], config['password'])
        global mqtt_api
        evcc_mqtt_api = self                    

        # TLS , not tested yet
        if config['tls'] == True:
            self.client.tls_set(config['tls']['ca_certs'], config['tls']['certfile'], config['tls']['keyfile'], cert_reqs=config['tls']['cert_reqs'], tls_version=config['tls']['tls_version'], ciphers=config['tls']['ciphers'])


        self.client.loop_start()
        self.client.connect(config['broker'], config['port'], 60)

        self.wait_ready()
        # Subscribe to status and loadpoint(s)
        self.client.subscribe(config['status_topic'])
        self.client.subscribe(config['loadpoint_topic'])
        self.client.message_callback_add(config['status_topic'], self._handle_message)
        self.client.message_callback_add(config['loadpoint_topic'], self._handle_message)

        return         
    
    def wait_ready(self) -> bool:
        retry = 30
        # Check if we are connected and wait for it
        while self.client.is_connected() == False:
            retry -= 1
            if retry == 0:
                logger.error(f'[EVCC] Could not connect to MQTT Broker')
                return False
            logger.info(f'[EVCC] Waiting for connection')
            time.sleep(1)

        return True
    
    def register_block_function(self, function):
        self.block_function = function
    
    def set_evcc_online(self, online:bool):
        if self.evcc_is_online != online:
            if online == False:
                logger.error(f'[EVCC] EVCC went offline')
                if self.evcc_is_charging == True:
                    # We remove the block, that we set to not end endless in block mode
                    logger.error(f'[EVCC] EVCC was charging, remove block')
                    self.evcc_is_charging = False
                    self.block_function(False)
            else: 
                logger.info(f'[EVCC] EVCC is online')
            self.evcc_is_online = online
        return

    def set_evcc_charging(self, charging:bool):
        if self.evcc_is_charging != charging:
            if charging == True:
                # We set the block, so we do not discharge the battery
                logger.info(f'[EVCC] EVCC is charging, set block')
                self.evcc_is_charging = True
                self.block_function(True)
            else:
                logger.info(f'[EVCC] EVCC is not charging, remove block')
                self.evcc_is_charging = False
                self.block_function(False)
        self.evcc_is_charging = charging
        return

    def handle_status_messages(self,  message):
        if message.payload == b'online':
            self.set_evcc_online(True)
        elif message.payload == b'offline':
            self.set_evcc_online(False)
        return
    
    def handle_charging_message(self, message):
        if re.match(b'true', message.payload, re.IGNORECASE):
            self.set_evcc_charging(True)
        elif re.match(b'false', message.payload, re.IGNORECASE):
            self.set_evcc_charging(False)
        return

    def _handle_message(self, client, userdata, message):
        logger.debug(f'[EVCC] Received message on {message.topic}')
        if message.topic == self.config['status_topic']:
            self.handle_status_messages(message)
        elif message.topic == self.config['loadpoint_topic']:
            self.handle_charging_message(message)
        else:
            logger.warning(f'[EVCC] No callback registered for {message.topic}')
        return