""""
Heatpump module

This module provides a factory class for creating instances of different types of heat pumps
based on the provided configuration. The supported heat pump types are 'thermia', 'dummy', 
and a default 'silent' type.

Classes:
    Heatpump: A factory class that returns an instance of a specific heat pump type based on 
              the provided configuration.

Dependencies:
    pytz: A library for accurate and cross platform timezone calculations.
"""

import pytz
from .dummy_heatpump import DummyHeatpump
from .silent_heatpump import SilentHeatpump
from .thermia_heatpump import ThermiaHeatpump


class Heatpump:
    """
    Heatpump class factory that returns an instance of a specific heat pump type
    based on the provided configuration.

    Args:
        config (dict): Configuration dictionary containing the type of heat pump and necessary
            credentials.
        timezone (pytz.timezone): Timezone information for the heat pump.

    Returns:
        ThermiaHeatpump: If the type specified in the config is 'thermia'.
        DummyHeatpump: If the type specified in the config is 'dummy'.
        SilentHeatpump: If the type specified in the config is neither 'thermia' nor 'dummy'.

    Raises:
        KeyError: If the 'type' key is not present in the config dictionary.
    """

    def __new__(cls, config: dict, timezone: pytz.timezone):
        if config is None: # pylint: disable=no-else-return
            return cls.default()
        elif "type" not in config:
            return cls.default()
        else:
            if config["type"].lower() == "thermia": # pylint: disable=no-else-return
                return ThermiaHeatpump(config, timezone)
            elif config["type"].lower() == "dummy":
                return DummyHeatpump()
            else:
                return cls.default()

    @staticmethod
    def default():
        """
        Create and return the default implementation, currently an instance of SilentHeatpump.

        Returns:
            SilentHeatpump: An instance of the SilentHeatpump class.
        """

        return SilentHeatpump()
