"""
SilentHeatpump Module

This module contains the SilentHeatpump class, which inherits from the HeatpumpBaseclass.
The SilentHeatpump class is a silent stub that does nothing and does not create any logging noise.

Classes:
    SilentHeatpump: A class that represents a silent heat pump with no operational functionality.

"""
import logging
from .baseclass import HeatpumpBaseclass

# Configure the logger
logger = logging.getLogger("__main__")


class SilentHeatpump(HeatpumpBaseclass):
    """
    SilentHeatpump class inherits from HeatpumpBaseclass and is a silent stub that
    does nothing and does not create any logging noise.
    """

    def __init__(self):
        logger.info("[SilentHeatpump] Initializing SilentHeatpump")
        pass # default impl does nothing,  pylint: disable=unnecessary-pass

    def activate_mqtt(self, mqtt_api):
        """
        Activates the MQTT functionality for the heat pump.

        Args:
            mqtt_api: An instance of the MQTT API to be used for communication.
        """
        pass # default impl does nothing,  pylint: disable=unnecessary-pass

    def refresh_api_values(self):
        pass

    def set_heatpump_parameters(self, net_consumption, prices):
        pass
