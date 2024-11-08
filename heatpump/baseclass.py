"""
Parent Class for implementing Heatpumps and test drivers
"""

import numpy as np
from mqtt_api import MqttApi


class HeatpumpBaseclass():
    """ "
    HeatpumpBaseclass is a base class for heat pump systems, providing a structure for implementing
    MQTT functionality, refreshing API values, generating MQTT topics,
    planning for high price windows, setting heat pump parameters, and shutting down the system.

    Methods:
        activate_mqtt(mqtt_api: mqtt_api.MqttApi):
            Activates the MQTT functionality for the heat pump. Must be implemented by subclasses.

        refresh_api_values():
            Refreshes the API values for the heat pump. Must be implemented by subclasses.

        _get_mqtt_topic() -> str:

        ensure_strategy_for_time_window(start_time: datetime, end_time: datetime):
            Plans for high price window. Must be implemented by subclasses.

        set_heatpump_parameters(net_consumption: np.ndarray, prices: dict):
            Sets the parameters for the heat pump based on net energy consumption and energy prices.
            Must be implemented by subclasses.

        shutdown():
            Shuts down the system, performing any necessary cleanup.
    """

    def activate_mqtt(self, mqtt_api: MqttApi):
        """
        Activates the MQTT functionality for the heat pump.

        This method should be implemented by subclasses to provide the specific
        MQTT activation logic.

        Args:
            mqtt_api (mqtt_api.MqttApi): An instance of the MqttApi class to handle
                                         MQTT operations.

        Raises:
            Error: If the method is not implemented by the subclass.
        """
        raise RuntimeError(
            "[Heatpump Base Class] Function 'activate_mqtt' not implemented"
        )

    def refresh_api_values(self):
        """
        Refreshes the API values for the heat pump.

        This method should be implemented by subclasses to update the heat pump's
        data from the API. If not implemented, it raises a RuntimeError.

        Raises:
            RuntimeError: If the method is not implemented in the subclass.
        """
        raise RuntimeError(
            "[Heatpump Base Class] Function 'refresh_api_values' not implemented"
        )

    # Used to implement the mqtt basic topic.
    # Currently there is only one Heatpump, so the number is hardcoded
    def _get_mqtt_topic(self):
        """
        Generates the MQTT topic for the heat pump.

        Returns:
            str: The MQTT topic string for the heat pump.
        """
        return "heatpumps/0/"

    def set_heatpump_parameters(self, net_consumption: np.ndarray, prices: dict):
        """
        Set the parameters for the heat pump based on net energy consumption and energy prices.
        Parameters:
        -----------
        net_consumption : np.ndarray
            An array representing the net energy consumption for each hour.
        prices : dict
            A dictionary where keys are hours and values are the corresponding energy prices.
        Returns:
        --------
        None
        """
        raise RuntimeError(
            "[Heatpump Base Class] Function 'set_heatpump_parameters' not implemented"
        )

    def shutdown(self):
        """
        Shuts down the system.

        This method is intended to perform any necessary cleanup and safely shut down the system.
        """
        pass  # default impl does nothing,  pylint: disable=unnecessary-pass
class NoHeatPumpsFoundException(Exception):
    """
    Exception raised when no heat pumps are found 
    in the configuration or the configured user account. 
    """

    def __init__(self, message="No heat pumps found in the configuration"):
        self.message = message
        super().__init__(self.message)
