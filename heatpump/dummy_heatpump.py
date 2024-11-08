"""
DummyHeatpump module

This module contains the DummyHeatpump class, which is a subclass of HeatpumpBaseclass.
It provides dummy implementations for various heat pump operations such as activating MQTT,
refreshing API values, planning for high price windows, and setting heat pump parameters.

Classes:
    DummyHeatpump: A dummy implementation of a heat pump for testing purposes.

"""

import logging
from .baseclass import HeatpumpBaseclass

# Configure the logger
logger = logging.getLogger("__main__")


class DummyHeatpump(HeatpumpBaseclass):
    """
    DummyHeatpump is a subclass of HeatpumpBaseclass
    that simulates the behavior of a heat pump for testing purposes.

    Methods:
        __init__():
            Initializes the DummyHeatpump instance.

        activate_mqtt(param):
            Activates MQTT for the DummyHeatpump and logs the MQTT topic.

        refresh_api_values():
            Refreshes the API values for the DummyHeatpump.

        ensure_strategy_for_time_window(start_time, end_time):
            Plans for a high price window between the specified start and end times.

        set_heatpump_parameters(net_consumption, prices):
            Sets the heat pump parameters using the provided net consumption and prices.
    """

    def __init__(self):
        pass

    def activate_mqtt(self, mqtt_api):
        logger.info("[DummyHeatpump] Activating MQTT with param: %s", mqtt_api)
        logger.debug("[DummyHeatpump] MQTT topic: %s", self._get_mqtt_topic())

    def refresh_api_values(self):
        logger.info("[DummyHeatpump] Refreshing API values")

    def set_heatpump_parameters(self, net_consumption, prices):
        logger.info(
            "[DummyHeatpump] Setting heat pump parameters with net consumption %s and prices %s",
            net_consumption,
            prices,
        )
