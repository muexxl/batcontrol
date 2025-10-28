"""
MQTT Inverter Driver for batcontrol

This driver enables batcontrol to integrate with any battery/inverter system via MQTT topics.
It acts as a generic bridge allowing external systems to provide battery state and receive
control commands over MQTT.

TOPIC STRUCTURE AND RETENTION REQUIREMENTS
===========================================

All topics follow the pattern: <base_topic>/<subtopic>

Status Topics (Inverter -> batcontrol):
---------------------------------------
These topics MUST be published as RETAINED by the external inverter/bridge
system:
- <base_topic>/status/capacity             - Battery capacity in Wh (float)

Optional status topics (also RETAINED):
- <base_topic>/status/min_soc              - Minimum SoC limit in %
                                             (float, 0-100)
- <base_topic>/status/max_soc              - Maximum SoC limit in %
                                             (float, 0-100)
- <base_topic>/status/max_charge_rate      - Maximum charge rate in W
                                             (float)
Update these topics at least every 2 minutes to ensure batcontrol has fresh data:

- <base_topic>/status/soc                  - State of Charge in %
                                             (float, 0-100)

Command Topics (batcontrol -> Inverter):
----------------------------------------
These topics are published by batcontrol and MUST NOT be retained:
- <base_topic>/command/mode                - Set mode:
                                             'force_charge',
                                             'allow_discharge',
                                             'avoid_discharge'
- <base_topic>/command/charge_rate         - Set charge rate in W
                                             (float)

WHY RETENTION MATTERS:
- Status topics MUST be RETAINED so batcontrol can read the current state
  immediately on startup
- Command topics MUST NOT be retained to avoid re-executing stale commands
  on reconnect
- If command topics are retained, the inverter may execute old commands
  after restart

CONFIGURATION EXAMPLE
=====================
```yaml
inverter:
  type: mqtt
  mqtt_broker: 192.168.1.100
  mqtt_port: 1883
  mqtt_user: batcontrol
  mqtt_password: secret
  base_topic: inverter
  capacity: 10000              # Battery capacity in Wh (required)
  min_soc: 5                   # Minimum SoC % (default: 5)
  max_soc: 100                 # Maximum SoC % (default: 100)
  max_grid_charge_rate: 5000   # Maximum charge rate in W (required)
```

EXTERNAL BRIDGE/INVERTER REQUIREMENTS
======================================

Your external system (inverter, bridge script, etc.) must:

1. Publish battery status as RETAINED messages:
   - Battery capacity in Wh
   - Current operating mode

2. Current soc as normal message (non-retained) to allow timely updates

3. Subscribe to command topics (non-retained):
   - Mode changes (force_charge, allow_discharge, avoid_discharge)
   - Charge rate adjustments

4. Handle reconnection gracefully:
   - Re-publish all status topics as RETAINED on reconnect
   - Don't retain command topics to avoid stale command execution

EXAMPLE BRIDGE IMPLEMENTATION (Python + paho-mqtt)
==================================================
```python
import paho.mqtt.client as mqtt

# Connect to MQTT broker
client = mqtt.Client()
client.username_pw_set("batcontrol", "secret")
client.connect("192.168.1.100", 1883, 60)

# Publish initial state (RETAINED)
client.publish("inverter/status/soc", "65.5")
client.publish("inverter/status/capacity", "10000", retain=True)
client.publish("inverter/status/min_soc", "5", retain=True)
client.publish("inverter/status/max_soc", "100", retain=True)
client.publish("inverter/status/max_charge_rate", "5000", retain=True)

# Subscribe to commands
def on_message(client, userdata, message):
    topic = message.topic
    value = message.payload.decode()

    if topic == "inverter/command/mode":
        print(f"Setting mode to: {value}")
        # Implement your inverter control here

    elif topic == "inverter/command/charge_rate":
        print(f"Setting charge rate to: {value}W")
        # Implement your charge rate control here

client.on_message = on_message
client.subscribe("inverter/command/#")
client.loop_forever()
```

LIMITATIONS
===========
- No bidirectional acknowledgment: batcontrol assumes commands succeed
- No auto-discovery: All topics must follow the documented structure
- Network dependency: MQTT broker must be reliable and accessible
- Initial state required: Status topics must be available at startup
- Clock sync: Ensure time sync between batcontrol and inverter for accurate scheduling
- QoS 1 for commands: Guarantees delivery but not exactly-once semantics

TROUBLESHOOTING
================
1. "No SOC data available":
   - Check that <base_topic>/status/soc is published as RETAINED
   - Verify MQTT broker connectivity and credentials
   - Check topic permissions

2. "Commands not executed":
   - Verify external system subscribes to <base_topic>/command/#
   - Check MQTT logs for delivery confirmation
   - Ensure external system is connected

3. "Stale commands after restart":
   - Verify command topics are NOT retained
   - Clear retained command topics: mosquitto_pub -r -n -t 'inverter/command/mode'

4. "State not updating":
   - Ensure external system publishes status regularly
   - Check for MQTT disconnections in logs
   - Verify status topics are RETAINED
"""

import logging
import time
from cachetools import TTLCache
import paho.mqtt.client as mqtt
from .baseclass import InverterBaseclass

logger = logging.getLogger(__name__)
logger.info('Loading module')


class MqttInverter(InverterBaseclass):
    """
    MQTT Inverter driver for batcontrol.

    Integrates external battery/inverter systems via MQTT topics.
    See module docstring for complete documentation on topics, retention, and configuration.
    """

    def __init__(self, config):
        """
        Initialize MQTT Inverter driver.

        Args:
            config (dict): Configuration dictionary containing:
                - mqtt_broker: MQTT broker hostname/IP (required)
                - mqtt_port: MQTT broker port (required)
                - mqtt_user: MQTT username (optional)
                - mqtt_password: MQTT password (optional)
                - base_topic: Base topic for all MQTT communication (required)
                - capacity: Battery capacity in Wh (required)
                - min_soc: Minimum SoC in % (default: 5)
                - max_soc: Maximum SoC in % (default: 95)
                - max_grid_charge_rate: Maximum charge rate in W (required)
                - cache_ttl: optional TTL for cached values in seconds (default: 120)
        """
        super().__init__(config)

        # Configuration
        self.mqtt_broker = config['mqtt_broker']
        self.mqtt_port = config['mqtt_port']
        self.mqtt_user = config.get('mqtt_user', None)
        self.mqtt_password = config.get('mqtt_password', None)
        self.base_topic = config['base_topic']
        self.cache_ttl = config.get('cache_ttl', 120)

        # Battery parameters (from config or defaults)
        self.min_soc = config.get('min_soc', 5)
        self.max_soc = config.get('max_soc', 100)

        # These values should be set in the config, if not throw ValueError
        if 'capacity' not in config:
            raise ValueError('Battery capacity must be specified in config')
        if 'max_grid_charge_rate' not in config:
            raise ValueError('Max grid charge rate must be specified in config')

        self.capacity = config.get('capacity')
        self.max_grid_charge_rate = config.get('max_grid_charge_rate')

        # Cached state from MQTT
        self.soc_value = TTLCache(maxsize=2, ttl=config.get('cache_ttl', 120))
        # use timestamp as key to store latest soc value
        self.soc_key = None
        self.charge_rate = 0  # Current charge rate in W

        # MQTT client setup
        self.mqtt_client = mqtt.Client()
        if self.mqtt_user and self.mqtt_password:
            self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)

        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message

        # Connect to broker
        try:
            logger.info('Connecting to MQTT broker %s:%d',
                       self.mqtt_broker, self.mqtt_port)
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            logger.error('Failed to connect to MQTT broker: %s', e)
            raise

        logger.info('MQTT Inverter initialized with base topic: %s',
                   self.base_topic)

    def _on_connect(self, client, userdata, flags, rc):  # pylint: disable=unused-argument
        """
        Callback when MQTT connection is established.
        Subscribes to all status topics.
        """
        if rc == 0:
            logger.info('Connected to MQTT broker successfully')
            # Subscribe to all status topics
            status_topic = f'{self.base_topic}/status/#'
            client.subscribe(status_topic)
            logger.debug('Subscribed to %s', status_topic)
        else:
            logger.error('Failed to connect to MQTT broker with code: %s', rc)

    def _on_message(self, client, userdata, message):  # pylint: disable=unused-argument
        """
        Callback for incoming MQTT messages.
        Updates cached state from status topics.
        """
        topic = message.topic
        payload = message.payload.decode('utf-8')

        logger.debug('Received MQTT message: %s = %s', topic, payload)

        try:
            # Parse topic
            if topic == f'{self.base_topic}/status/soc':
                new_soc_key = time.time()
                self.soc_value[new_soc_key] = float(payload)
                self.soc_key = new_soc_key
                logger.debug('Updated SOC: %s%%', self.soc_value)

            elif topic == f'{self.base_topic}/status/capacity':
                self.capacity = float(payload)
                logger.debug('Updated capacity: %s Wh', self.capacity)
            elif topic == f'{self.base_topic}/status/min_soc':
                self.min_soc = float(payload)
                logger.debug('Updated min_soc: %s%%', self.min_soc)

            elif topic == f'{self.base_topic}/status/max_soc':
                self.max_soc = float(payload)
                logger.debug('Updated max_soc: %s%%', self.max_soc)

            elif topic == f'{self.base_topic}/status/max_charge_rate':
                self.max_grid_charge_rate = float(payload)
                logger.debug('Updated max_charge_rate: %s W',
                           self.max_grid_charge_rate)

        except (ValueError, TypeError) as e:
            logger.error('Error parsing MQTT message %s: %s', topic, e)

    def set_mode_force_charge(self, chargerate=500):
        """
        Set inverter to force charge mode.

        Publishes mode and charge rate to MQTT command topics (non-retained).

        Args:
            chargerate (float): Charge rate in W
        """
        self.mode = 'force_charge'
        logger.info('Setting mode to force_charge with rate %sW', chargerate)

        # Publish mode command (QoS 1, not retained)
        self.mqtt_client.publish(
            f'{self.base_topic}/command/mode',
            'force_charge',
            qos=1,
            retain=False
        )

        # Publish charge rate command (QoS 1, not retained)
        self.mqtt_client.publish(
            f'{self.base_topic}/command/charge_rate',
            str(chargerate),
            qos=1,
            retain=False
        )
        self.charge_rate = chargerate

    def set_mode_allow_discharge(self):
        """
        Set inverter to allow discharge mode.

        Publishes mode to MQTT command topic (non-retained).
        """
        self.mode = 'allow_discharge'
        logger.info('Setting mode to allow_discharge')

        # Publish mode command (QoS 1, not retained)
        self.mqtt_client.publish(
            f'{self.base_topic}/command/mode',
            'allow_discharge',
            qos=1,
            retain=False
        )

    def set_mode_avoid_discharge(self):
        """
        Set inverter to avoid discharge mode.

        Publishes mode to MQTT command topic (non-retained).
        """
        self.mode = 'avoid_discharge'
        logger.info('Setting mode to avoid_discharge')

        # Publish mode command (QoS 1, not retained)
        self.mqtt_client.publish(
            f'{self.base_topic}/command/mode',
            'avoid_discharge',
            qos=1,
            retain=False
        )

    def get_capacity(self):
        """
        Get battery capacity in Wh.

        Returns:
            float: Battery capacity in Wh
        """
        return self.capacity

    def get_SOC(self):  # pylint: disable=invalid-name
        """
        Get current state of charge.

        Returns:
            float: State of charge in percentage (0-100)
        """

        soc_value = None
        while soc_value is None:
            if self.soc_key and self.soc_key in self.soc_value:
                soc_value = self.soc_value[self.soc_key]
                logger.debug('Current SOC value: %s', soc_value)
            else:
                logger.warning('No SOC data available from MQTT, waiting...')
                time.sleep(1)  # Wait before retrying

        return soc_value

    def activate_mqtt(self, api_mqtt_api):
        """
        Activate batcontrol's MQTT API for publishing inverter state.

        This allows batcontrol to publish inverter state to its own MQTT topics
        (separate from the inverter control topics).

        Args:
            api_mqtt_api: The MQTT API instance from batcontrol
        """
        self.mqtt_api = api_mqtt_api
        logger.debug('MQTT API activated for MQTT inverter')

    def refresh_api_values(self):
        """
        Publish current values to batcontrol's MQTT API.

        This is separate from the inverter MQTT topics - it publishes to
        batcontrol's own MQTT topic structure for monitoring/visualization.
        """
        # Parent class handles standard MQTT publishing
        if self.mqtt_api:
            # Call parent to publish standard metrics
            super().refresh_api_values()

    def shutdown(self):
        """
        Cleanly shutdown the MQTT connection.

        Disconnects from MQTT broker and stops the network loop.
        """
        logger.info('Shutting down MQTT Inverter')
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logger.info('MQTT Inverter shutdown complete')
        except ConnectionError as e:
            logger.error('Error during MQTT Inverter shutdown: %s', e)
