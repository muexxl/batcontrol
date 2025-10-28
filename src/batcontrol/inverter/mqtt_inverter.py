"""
MQTT Inverter Driver for batcontrol

This driver enables batcontrol to integrate with any battery/inverter system via MQTT topics.
It acts as a generic bridge allowing external systems to provide battery state and receive
control commands over MQTT.

ARCHITECTURE
============
This driver uses batcontrol's shared MQTT connection (configured in the main batcontrol MQTT API).
It does NOT create a separate MQTT client. Instead, it subscribes to inverter-specific topics
using the existing connection. This ensures:
- Single MQTT connection per batcontrol instance
- Consistent MQTT broker configuration
- Shared connection pool and resources
- Unified logging and error handling

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
Note: MQTT connection settings (broker, port, credentials) are configured in batcontrol's
main MQTT API section, not in the inverter configuration.

```yaml
# Main batcontrol MQTT configuration
mqtt:
  broker: 192.168.1.100
  port: 1883
  user: batcontrol
  password: secret

# Inverter configuration
inverter:
  type: mqtt
  base_topic: inverter         # Base topic for inverter communication (required)
  capacity: 10000              # Battery capacity in Wh (required)
  min_soc: 5                   # Minimum SoC % (default: 5)
  max_soc: 100                 # Maximum SoC % (default: 100)
  max_grid_charge_rate: 5000   # Maximum charge rate in W (required)
  cache_ttl: 120               # Cache TTL for SOC values in seconds (default: 120)
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

        Note: MQTT connection is provided by batcontrol's MQTT API and configured there.
        This driver only needs inverter-specific configuration.

        Args:
            config (dict): Configuration dictionary containing:
                - base_topic: Base topic for all MQTT communication (required)
                - capacity: Battery capacity in Wh (required)
                - min_soc: Minimum SoC in % (default: 5)
                - max_soc: Maximum SoC in % (default: 100)
                - max_grid_charge_rate: Maximum charge rate in W (required)
                - cache_ttl: optional TTL for cached values in seconds (default: 120)
        """
        super().__init__(config)

        # Configuration
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

        self.last_mode = "allow_discharge"

        # Cached state from MQTT
        self.soc_value = TTLCache(maxsize=2, ttl=config.get('cache_ttl', 120))
        # use timestamp as key to store latest soc value
        self.soc_key = None
        self.charge_rate = 0  # Current charge rate in W

        # MQTT client reference (will be set via activate_mqtt)
        self.mqtt_client = None
        self.mqtt_api = None

        logger.info('MQTT Inverter initialized with base topic: %s (waiting for MQTT API connection)',
                   self.base_topic)

    def _setup_subscriptions(self):
        """
        Subscribe to all status topics.
        Called after MQTT API is activated.
        """
        if self.mqtt_client:
            status_topic = f'{self.base_topic}/status/#'
            self.mqtt_client.subscribe(status_topic)
            self.mqtt_client.message_callback_add(f'{self.base_topic}/status/#', self._on_message)
            logger.info('Subscribed to %s', status_topic)

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
        self.last_mode = 'force_charge'
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
        self.last_mode = 'allow_discharge'
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
        self.last_mode = 'avoid_discharge'
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
        Activate batcontrol's MQTT API for publishing inverter state and control.

        Uses the shared MQTT connection from batcontrol's MQTT API for both
        publishing inverter state and subscribing to inverter control topics.

        Args:
            api_mqtt_api: The MQTT API instance from batcontrol
        """
        self.mqtt_api = api_mqtt_api
        self.mqtt_client = api_mqtt_api.client

        # Setup subscriptions for inverter control topics
        self._setup_subscriptions()

        logger.info('MQTT API activated for MQTT inverter on base topic: %s', self.base_topic)

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
        Cleanly shutdown the MQTT Inverter.

        Note: MQTT connection is managed by batcontrol's MQTT API,
        so we don't disconnect here.
        """
        logger.info('Shutting down MQTT Inverter')
        # Unsubscribe from topics
        if self.mqtt_client:
            try:
                status_topic = f'{self.base_topic}/status/#'
                self.mqtt_client.unsubscribe(status_topic)
                logger.info('Unsubscribed from %s', status_topic)
            except Exception as e:
                logger.error('Error during MQTT Inverter shutdown: %s', e)
        logger.info('MQTT Inverter shutdown complete')
