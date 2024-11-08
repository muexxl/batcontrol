# pylint: disable=too-many-lines
# pylint: disable=wrong-import-position
"""
This module provides classes and methods for managing and controlling a Thermia heat pump system, 
including handling high price periods and applying various strategies based on energy consumption 
and prices.
Classes:
    ThermiaHighPriceHandling: Represents an applied setting to handle high price periods 
                              for the Thermia heat pump system.
    ThermiaStrategySlot: Represents a strategy decision for a certain time slot.
    ThermiaHeatpump: Manages and controls a Thermia heat pump, 
                     providing methods to initialize the heat pump, 
                     fetch configuration parameters, 
                     activate MQTT, refresh API values, 
                     set heat pump parameters, adjust mode duration, 
                     apply modes, ensure strategies for time windows, 
                     install schedules, clean up high price strategies and handlers, 
                     and publish strategies to MQTT.
    logger: Logger instance for logging messages.
"""

from dataclasses import dataclass
import inspect
import logging
import datetime
from typing import Optional
import sys
import os
import pytz
import numpy as np


logger = logging.getLogger("__main__")
logger.info("[Heatpump] loading module ")

#### hack to add the submodule to the python path before import fails
if os.path.isdir("thermia_online_api") and os.path.exists("thermia_online_api/ThermiaOnlineAPI"):
    sys.path.append(os.path.abspath("thermia_online_api"))
    logger.warning("ThermiaOnlineAPI module added to Python path from 'thermia_online_api' "
                   +"subdirectory. This is a hack because of the forked library being "
                   +"integrated as submodule in a subdir instead of root dir.")

from ThermiaOnlineAPI.const import (
    CAL_FUNCTION_EVU_MODE,
    CAL_FUNCTION_HOT_WATER_BLOCK,
    CAL_FUNCTION_REDUCED_HEATING_EFFECT,
)
from ThermiaOnlineAPI.model.HeatPump import ThermiaHeatPump
from ThermiaOnlineAPI.model.CalendarSchedule import CalendarSchedule
from ThermiaOnlineAPI import Thermia
from ThermiaOnlineAPI.utils import utils

from mqtt_api import MqttApi
from .baseclass import HeatpumpBaseclass, NoHeatPumpsFoundException



@dataclass
class ThermiaHighPriceHandling:
    """
    A class representing an applied setting to handle high price periods
    for the Thermia heat pump system.

    Attributes:
        start_time (datetime.datetime): The start time of the high price period.
        end_time (datetime.datetime): The end time of the high price period.
        schedule (CalendarSchedule): The schedule associated with the high price period.
    """

    def __init__(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        schedule: CalendarSchedule,
    ):
        """
        Initializes the ThermiaHighPriceHandling class with the specified
        start time, end time, and schedule.

        Args:
            start_time (datetime.datetime): The start time of the high price period.
            end_time (datetime.datetime): The end time of the high price period.
            schedule (CalendarSchedule): The schedule associated with the high price period.
        """

        self.start_time = start_time
        self.end_time = end_time
        self.schedule = schedule

    def __repr__(self):
        return f"HighPriceHandlingStrategy(schedule={self.schedule})"


@dataclass
class ThermiaStrategySlot:
    """
    A class to represent a strategy decision for a certain time slot.

    Attributes:
    -----------
    start_time : datetime.datetime
        The start time of the strategy slot.
    end_time : datetime.datetime
        The end time of the strategy slot.
    mode : str
        The mode of operation during the strategy slot.
    price : float
        The price associated with the strategy slot.
    consumption : float
        The energy consumption during the strategy slot.

    Methods:
    --------
    setHandling(handler: ThermiaHighPriceHandling):
        Sets the handler for high price handling.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        mode: str,
        price: float,
        consumption: float,
    ):
        """
        Initialize a new instance of the Thermia class.

        Args:
            start_time (datetime.datetime): The start time of the heat pump operation.
            end_time (datetime.datetime): The end time of the heat pump operation.
            mode (str): The mode of operation for the heat pump.
            price (float): The price of electricity during the operation period.
            consumption (float): The energy consumption of the heat pump during
                                the operation period.
        """
        self.start_time = start_time
        self.end_time = end_time
        self.mode = mode
        self.price = price
        self.consumption = consumption
        self.handler = None

    def associate_handler(self, handler: ThermiaHighPriceHandling):
        """
        Sets the handler for high price handling.

        Args:
            handler (ThermiaHighPriceHandling): An instance of ThermiaHighPriceHandling
                                                that defines how to handle high price situations.
        """
        self.handler = handler

    def __repr__(self):
        if hasattr(self, "handler"):  # pylint: disable=no-else-return
            return (
                f"STRATEGY({self.start_time}-{self.end_time}:"
                + f"[{self.mode}]->{self.handler.schedule})"
            )
        else:
            return f"STRATEGY({self.start_time}-{self.end_time}:[{self.mode}])"




class ThermiaHeatpump(
    HeatpumpBaseclass
):  # pylint: disable=too-many-instance-attributes
    """
    ThermiaHeatpump class for managing and controlling a Thermia heat pump.

    This class provides methods to initialize the heat pump, fetch configuration parameters,
    ensure connection to the heat pump, activate MQTT, refresh API values, set heat pump parameters,
    adjust mode duration, apply modes, ensure strategies for time windows,
    install schedules in the heat pump, clean up high price strategies and handlers,
    and publish strategies to MQTT.

    Attributes:
    heat_pump : Optional[ThermiaHeatPump]
        Instance of the Thermia heat pump.
    mqtt_client : Optional[MQTT_API]
        MQTT client for publishing internal values.
    high_price_handlers : dict[datetime.datetime, ThermiaHighPriceHandling]
        Dictionary to store high price handlers to avoid duplicates and enable removal.
    already_planned_until : datetime
        Maximum time that has already been planned to avoid double planning.
    high_price_strategies : dict[datetime.datetime, ThermiaStrategySlot]
        Dictionary to store all strategies for future reference.
    min_price_for_evu_block : float
        Minimum price for EVU block mode.
    max_evu_block_hours : int
        Maximum number of hours for EVU block mode.
    max_evu_block_duration : int
        Maximum duration for EVU block mode.
    min_price_for_hot_water_block : float
        Minimum price for hot water block mode.
    max_hot_water_block_hours : int
        Maximum number of hours for hot water block mode.
    max_hot_water_block_duration : int
        Maximum duration for hot water block mode.
    min_price_for_reduced_heat : float
        Minimum price for reduced heat mode.
    max_reduced_heat_hours : int
        Maximum number of hours for reduced heat mode.
    max_reduced_heat_duration : int
        Maximum duration for reduced heat mode.
    reduced_heat_temperature : int
        Temperature for reduced heat mode.
    max_price_for_increased_heat : float
        Maximum price for increased heat mode.
    min_energy_surplus_for_increased_heat : int
        Minimum energy surplus for increased heat mode.
    max_increased_heat_hours : int
        Maximum number of hours for increased heat mode.
    max_increased_heat_duration : int
        Maximum duration for increased heat mode.
    increased_heat_temperature : int
        Temperature for increased heat mode.
    max_increased_heat_outdoor_temperature : int
        Maximum outdoor temperature for increased heat mode.
    min_energy_surplus_for_hot_water_boost : int
        Minimum energy surplus for hot water boost mode.
    max_hot_water_boost_hours : int
        Maximum number of hours for hot water boost mode.

    Methods:
    __init__(config: dict, timezone: pytz.timezone) -> None
    fetch_param_from_config(config: dict, name: str, default: float) -> float
        Fetch a parameter from the configuration dictionary.
    ensure_connection()
        Ensure connection to the Thermia heat pump.
    activate_mqtt(api_mqtt_api)
        Activate MQTT and publish internal values.
    refresh_api_values()
        Refresh API values and publish them to MQTT.
    set_heatpump_parameters(net_consumption: np.ndarray, prices: dict)
    adjust_mode_duration(heat_modes: list[str], prices: list[float],
        inspected_mode: str, downgrade_mode: str, max_mode_duration: int)
    applyMode(mode: str, start_index: int, end_index: int)
        Apply the specified mode for the given time range.
    ensure_strategy_for_time_window(start_time: datetime, end_time: datetime, mode: str)
        Ensure a strategy is present for the specified time window.
    install_schedule_in_heatpump(start_time: datetime, end_time: datetime, mode: str)
        Install a schedule in the heat pump based on the provided start time, end time, and mode.
    cleanupHighPriceStrategies()
    cleanupHighPriceHandlers()
    publish_strategies_to_mqtt()
        Publish high price strategies and handlers to MQTT.
    __del__()
    """

    heat_pump: Optional[ThermiaHeatPump] = None
    mqtt_client: Optional[MqttApi] = None

    ## store all high price handlers to avoid duplicates and to be able to remove them
    high_price_handlers: dict[datetime.datetime, ThermiaHighPriceHandling] = {}

    ## max time that has already been planned, to avoid double planning
    already_planned_until: datetime

    ## store all strategies to be able to refer to them later
    high_price_strategies: dict[datetime.datetime, ThermiaStrategySlot] = {}

    ## config for the strategy
    # Set the maximum number of hours and the maximum duration for each mode
    # The strategy is to set the heat pump to the most energy saving mode in time slots
    # with the highest price first, but having a maximum number of hours and a
    # maximum duration for each mode
    # and having a min trigger price for each mode
    ### EVU Block
    min_price_for_evu_block = 0.6
    max_evu_block_hours = 14
    max_evu_block_duration = 6
    ### Hot Water Block
    min_price_for_hot_water_block = 0.4
    max_hot_water_block_hours = 10
    max_hot_water_block_duration = 4
    ### Reduced Heat
    min_price_for_reduced_heat = 0.3
    max_reduced_heat_hours = 14
    max_reduced_heat_duration = 6
    reduced_heat_temperature = 18
    ### Increased Heat
    max_price_for_increased_heat = 0.2
    min_energy_surplus_for_increased_heat = 500
    max_increased_heat_hours = 14
    max_increased_heat_duration = 6
    increased_heat_temperature = 22
    max_increased_heat_outdoor_temperature = 15
    ### Hot Water Boost
    min_energy_surplus_for_hot_water_boost = 2500
    max_hot_water_boost_hours = 1

    def __init__(self, config: dict, timezone: pytz.timezone) -> None:
        """
        Initialize the ThermiaHeatpump instance.

        Parameters:
        -----------
        config : dict
            Configuration dictionary containing user credentials and other settings.
        timezone : pytz.timezone
            Timezone of the heat pump installation.
        """
        super().__init__()
        self.user = config["user"]
        self.password = config["password"]
        self.__ensure_connection()
        self.batcontrol_timezone = timezone
        self.already_planned_until = (
            datetime.datetime.now()
            .astimezone(self.batcontrol_timezone)
            .replace(minute=0, second=0, microsecond=0)
        )

        ## fetch strategy params from config
        ### EVU Block
        self.min_price_for_evu_block = self.__fetch_param_from_config(
            config, "min_price_for_evu_block", 0.6
        )
        self.max_evu_block_hours = self.__fetch_param_from_config(
            config, "max_evu_block_hours", 14
        )
        self.max_evu_block_duration = self.__fetch_param_from_config(
            config, "max_evu_block_duration", 6
        )
        ### Hot Water Block
        self.min_price_for_hot_water_block = self.__fetch_param_from_config(
            config, "min_price_for_hot_water_block", 0.4
        )
        self.max_hot_water_block_hours = self.__fetch_param_from_config(
            config, "max_hot_water_block_hours", 10
        )
        self.max_hot_water_block_duration = self.__fetch_param_from_config(
            config, "max_hot_water_block_duration", 4
        )
        ### Reduced Heat
        self.min_price_for_reduced_heat = self.__fetch_param_from_config(
            config, "min_price_for_reduced_heat", 0.3
        )
        self.max_reduced_heat_hours = self.__fetch_param_from_config(
            config, "max_reduced_heat_hours", 14
        )
        self.max_reduced_heat_duration = self.__fetch_param_from_config(
            config, "max_reduced_heat_duration", 6
        )
        self.reduced_heat_temperature = self.__fetch_param_from_config(
            config, "reduced_heat_temperature", 20
        )
        ### Increased Heat
        self.max_price_for_increased_heat = self.__fetch_param_from_config(
            config, "max_price_for_increased_heat", 0.2
        )
        self.min_energy_surplus_for_increased_heat = self.__fetch_param_from_config(
            config, "min_energy_surplus_for_increased_heat", 1000
        )
        self.max_increased_heat_hours = self.__fetch_param_from_config(
            config, "max_increased_heat_hours", 14
        )
        self.max_increased_heat_duration = self.__fetch_param_from_config(
            config, "max_increased_heat_duration", 6
        )
        self.increased_heat_temperature = self.__fetch_param_from_config(
            config, "increased_heat_temperature", 22
        )
        self.max_increased_heat_outdoor_temperature = self.__fetch_param_from_config(
            config, "max_increased_heat_outdoor_temperature", 15
        )
        ### Hot Water Boost
        self.min_energy_surplus_for_hot_water_boost = self.__fetch_param_from_config(
            config, "min_energy_surplus_for_hot_water_boost", 2500
        )
        self.max_hot_water_boost_hours = self.__fetch_param_from_config(
            config, "max_hot_water_boost_hours", 1
        )

    def __fetch_param_from_config(
        self, config: dict, name: str, default: float
    ) -> float:
        """
        Fetches a parameter from the configuration dictionary. If the parameter
        is not found, returns the provided default value.

        Args:
            config (dict): The configuration dictionary to fetch the parameter from.
            name (str): The name of the parameter to fetch.
            default (float): The default value to return if the parameter is not found.

        Returns:
            float: The value of the parameter from the configuration, or the default value.
        """

        if name in config:  # pylint: disable=no-else-return
            logger.debug(
                "[ThermiaHeatpump] fetching %s from config: %s", name, config[name]
            )
            return config[name]
        else:
            logger.debug(
                "[ThermiaHeatpump] using default for config %s  default: %s",
                name,
                default,
            )
            return default

    def __ensure_connection(self):
        """
        Ensures that a connection to the Thermia heat pump is established.

        This method attempts to connect to the Thermia heat pump using the provided
        user credentials. If a connection is successfully established, it initializes
        the heat pump and logs relevant information. If no heat pumps are found in the
        account or if any other exception occurs during the connection process, it logs
        an error message and sets the heat pump attribute to None.

        Raises:
            Exception: If no heat pumps are found in the account.
        """
        if not self.heat_pump:
            try:
                thermia = Thermia(self.user, self.password)
                logger.debug("[ThermiaHeatpump] Connected: %s", str(thermia.connected))

                if not thermia.heat_pumps:
                    raise NoHeatPumpsFoundException("No heat pumps found in account")
                heat_pump = thermia.heat_pumps[0]
                self.heat_pump = heat_pump
                logger.debug(
                    "[ThermiaHeatpump] initialized HeatPump %s", str(self.heat_pump)
                )
                logger.debug(
                    "[ThermiaHeatpump] current supply line temperature: %s",
                    str(heat_pump.supply_line_temperature),
                )
            except NoHeatPumpsFoundException as e:
                logger.error("[ThermiaHeatpump] No heat pumps found: %s", e)
                self.heat_pump = None
            except ConnectionError as e:
                logger.error("[ThermiaHeatpump] Connection error: %s", e)
                self.heat_pump = None
            except Exception as e:  # pylint: disable=broad-except
                logger.error("[ThermiaHeatpump] Unexpected error: %s", e)
                self.heat_pump = None

    # Start API functions
    # MQTT publishes all internal values.
    #
    # Topic is: base_topic + '/heatpumps/0/'
    #
    def activate_mqtt(self, mqtt_api: MqttApi):
        """
        Activate MQTT and publish internal values.

        Args:
            api_mqtt_api (mqtt_api.MqttApi): The MQTT API client to use for publishing values.
        """

        self.mqtt_client = mqtt_api
        logger.info("[ThermiaHeatpump]  Activating MQTT")
        logger.debug("[ThermiaHeatpump] MQTT topic: %s", self._get_mqtt_topic())

    def refresh_api_values(self):
        """
        Refresh API values and publish them to MQTT.

        This method ensures the connection to the heat pump, updates the heat pump data,
        and publishes the updated values to the MQTT client. It also publishes the configuration
        values to the MQTT client.

        Args:
            None

        Returns:
            None
        """

        logger.debug("[ThermiaHeatpump] Refreshing API values")
        self.__ensure_connection()

        if self.mqtt_client and self.heat_pump:
            try:
                self.heat_pump.update_data()
                self.mqtt_client.generic_publish(
                    self._get_mqtt_topic() + "xx_supply_line_temperature",
                    self.heat_pump.supply_line_temperature,
                )
                for name, value in self._get_all_properties(self.heat_pump):
                    # Ensure the value is a supported type
                    if not isinstance(value, (str, bytearray, int, float, type(None))):
                        value = str(value)
                    self.mqtt_client.generic_publish(
                        self._get_mqtt_topic() + name, value
                    )
                logger.debug("[ThermiaHeatpump] API values refreshed")

                # Publish all config values with config/ prefix
                config_topic_prefix = self._get_mqtt_topic() + "config/"
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "min_price_for_evu_block",
                    self.min_price_for_evu_block,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_evu_block_hours",
                    self.max_evu_block_hours,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_evu_block_duration",
                    self.max_evu_block_duration,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "min_price_for_hot_water_block",
                    self.min_price_for_hot_water_block,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_hot_water_block_hours",
                    self.max_hot_water_block_hours,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_hot_water_block_duration",
                    self.max_hot_water_block_duration,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "min_price_for_reduced_heat",
                    self.min_price_for_reduced_heat,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_reduced_heat_hours",
                    self.max_reduced_heat_hours,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "reduced_heat_temperature",
                    self.reduced_heat_temperature,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_price_for_increased_heat",
                    self.max_price_for_increased_heat,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "min_energy_surplus_for_increased_heat",
                    self.min_energy_surplus_for_increased_heat,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_increased_heat_hours",
                    self.max_increased_heat_hours,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_increased_heat_duration",
                    self.max_increased_heat_duration,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "increased_heat_temperature",
                    self.increased_heat_temperature,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_increased_heat_outdoor_temperature",
                    self.max_increased_heat_outdoor_temperature,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "min_energy_surplus_for_hot_water_boost",
                    self.min_energy_surplus_for_hot_water_boost,
                )
                self.mqtt_client.generic_publish(
                    config_topic_prefix + "max_hot_water_boost_hours",
                    self.max_hot_water_boost_hours,
                )

                logger.debug("[ThermiaHeatpump] config values published to MQTT  ...")

            except Exception as e:  # pylint: disable=broad-except
                logger.error("[ThermiaHeatpump] Failed to refresh API values: %s", e)

    def _get_all_properties(self, obj):
        for name, method in inspect.getmembers( # pylint: disable=unused-variable
            obj.__class__, lambda m: isinstance(m, property)
        ):
            yield name, getattr(obj, name)

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
        Notes:
        ------
        This method determines the operating mode of the heat pump for each hour
        based on the net energy consumption and energy prices.
        The modes are:
            - "W": Hot water boost
            - "H": Heat increased temperature
            - "N": Heat normal
            - "R": Heat reduced temperature
            - "B": Hot water block
            - "E": EVU Block
        The method logs the decision-making process and applies the determined
        modes over continuous time windows.
        """
        # ensure availability of data
        max_hour = min(len(net_consumption), len(prices))

        duration = datetime.timedelta(
            hours=max_hour
        )  # add one hour to include the druartion of evenan single 1-hour slot

        curr_hour_start = (
            datetime.datetime.now()
            .astimezone(self.batcontrol_timezone)
            .replace(minute=0, second=0, microsecond=0)
        )

        max_timestamp = curr_hour_start + duration
        if self.heat_pump is not None and max_timestamp > self.already_planned_until:
            logger.debug("[ThermiaHeatpump] Planning until %s", max_timestamp)
            ## for now we do a full replan
            self.high_price_strategies = {}
            for start_time, handler in self.high_price_handlers.items():
                self.heat_pump.delete_schedule(handler.schedule)
                logger.debug(
                    "[ThermiaHeatpump] Replan from scratch: Deleted High Price Handler %s",
                    handler.schedule,
                )
            self.high_price_handlers = {}
            # fetch the current state of the heat pump and
            # calendars and check if they are still valid
            #
            # - if expired, delete them
            # - also delete all schedules tat are in the time window we consider in this planning

            current_schedules = self.heat_pump.get_schedules()
            for schedule in current_schedules:
                if (
                    schedule.start.timestamp() >= curr_hour_start.timestamp()
                    and schedule.start.timestamp() <= max_timestamp.timestamp()
                ):
                    self.heat_pump.delete_schedule(schedule)
                    logger.debug(
                        "[ThermiaHeatpump] Replan from scratch: Deleted conflicting schedule %s",
                        schedule,
                    )
                elif schedule.end.timestamp() < curr_hour_start.timestamp():
                    self.heat_pump.delete_schedule(schedule)
                    logger.debug(
                        "[ThermiaHeatpump] Replan from scratch: Deleted expired schedule %s",
                        schedule,
                    )
                else:
                    logger.debug(
                        "[ThermiaHeatpump] Replan from scratch: Keeping schedule %s",
                        schedule,
                    )

            # TODO: summer mode would try to match heat pump energy demand and PV surplus
            # assumed_hourly_heatpump_energy_demand = 500  # watthour
            # assumed_hotwater_reheat_energy_demand = 1500  # watthour
            # assumed_hotwater_boost_energy_demand = 1500  # watthour

            heat_modes = ["N"] * max_hour

            # Sort hours by highest prices descending
            sorted_hours_by_price = sorted(
                range(max_hour), key=lambda h: prices[h], reverse=True
            )

            ### counters for this evaluation
            remaining_evu_block_hours = self.max_evu_block_hours
            remaining_hot_water_block_hours = self.max_hot_water_block_hours
            remaining_reduced_heat_hours = self.max_reduced_heat_hours
            remaining_increased_heat_hours = self.max_increased_heat_hours
            remaining_hot_water_boost_hours = self.max_hot_water_boost_hours

            # Iterate over hours sorted by price and set modes
            # based on trigger price and max hours per day limits
            for h in sorted_hours_by_price:
                if (
                    net_consumption[h] < -self.min_energy_surplus_for_hot_water_boost
                    and remaining_hot_water_boost_hours > 0
                ):
                    heat_modes[h] = "W"
                    remaining_hot_water_boost_hours -= 1
                    logger.debug(
                        "[ThermiaHeatpump] Set Hot Water Boost at +%dh due to high surplus %s",
                        h,
                        net_consumption[h],
                    )
                elif (
                    net_consumption[h] < -self.min_energy_surplus_for_increased_heat
                    or prices[h] <= self.max_price_for_increased_heat
                    and remaining_increased_heat_hours > 0
                ):
                    if (
                        self.heat_pump.outdoor_temperature
                        < self.max_increased_heat_outdoor_temperature
                    ):
                        heat_modes[h] = "H"
                        remaining_increased_heat_hours -= 1
                        if prices[h] <= self.max_price_for_increased_heat:
                            logger.debug(
                                "[ThermiaHeatpump] Set Increased Heat at +%dh due to low price "
                                + "%s and low outdoor temperature %s",
                                h,
                                prices[h],
                                self.heat_pump.outdoor_temperature,
                            )
                        else:
                            logger.debug(
                                "[ThermiaHeatpump] Set Increased Heat at +%dh due to high surplus "
                                + "%s and low outdoor temperature %s",
                                h,
                                net_consumption[h],
                                self.heat_pump.outdoor_temperature,
                            )
                    else:
                        heat_modes[h] = "N"
                        logger.debug(
                            "[ThermiaHeatpump] Set Normal Heat at +%dh due to high surplus "
                            + "%s and high outdoor temperature %s",
                            h,
                            net_consumption[h],
                            self.heat_pump.outdoor_temperature,
                        )
                elif (
                    prices[h] >= self.min_price_for_evu_block
                    and remaining_evu_block_hours > 0
                ):
                    heat_modes[h] = "E"
                    remaining_evu_block_hours -= 1
                    logger.debug(
                        "[ThermiaHeatpump] Set EVU Block at +%dh due to high price %s",
                        h,
                        prices[h],
                    )
                elif (
                    prices[h] >= self.min_price_for_hot_water_block
                    and remaining_hot_water_block_hours > 0
                ):
                    heat_modes[h] = "B"
                    remaining_hot_water_block_hours -= 1
                    logger.debug(
                        "[ThermiaHeatpump] Set Hot Water Block at +%dh due to high price %s",
                        h,
                        prices[h],
                    )
                elif (
                    prices[h] >= self.min_price_for_reduced_heat
                    and remaining_reduced_heat_hours > 0
                ):
                    heat_modes[h] = "R"
                    remaining_reduced_heat_hours -= 1
                    logger.debug(
                        "[ThermiaHeatpump] Set Reduced Heat at +%dh due to high price %s",
                        h,
                        prices[h],
                    )
                else:
                    heat_modes[h] = "N"
                    logger.debug(
                        "[ThermiaHeatpump] Set Normal Heat at +%dh due to price %s",
                        h,
                        prices[h],
                    )

            # Evaluate the duration of each mode and downgrade to lower mode if necessary
            self.adjust_mode_duration(
                heat_modes, prices, "E", "B", self.max_evu_block_duration
            )
            self.adjust_mode_duration(
                heat_modes, prices, "B", "R", self.max_hot_water_block_duration
            )
            self.adjust_mode_duration(
                heat_modes, prices, "R", "N", self.max_reduced_heat_duration
            )
            self.adjust_mode_duration(
                heat_modes, prices, "H", "N", self.max_increased_heat_duration
            )

            logger.debug("[ThermiaHeatpump] Adjusted Heatpump Modes: %s", heat_modes)

            # Iterate over heat modes and handle windows of equal mode
            start_index = 0
            current_mode = heat_modes[0]

            # -------- here we start to convert indices into timestamps

            for i in range(1, max_hour):
                if heat_modes[i] != current_mode:
                    # Handle the range from start_index to i-1
                    self.apply_mode(current_mode, start_index, i - 1)
                    start_index = i
                    current_mode = heat_modes[i]
            # Handle the last range
            self.apply_mode(current_mode, start_index, max_hour)

            for i in range(max_hour):
                hours_until_range_start = datetime.timedelta(hours=i)
                range_duration = datetime.timedelta(
                    hours=1
                )  # add one hour to include the duration of evenan single 1-hour slot

                curr_hour_start = (
                    datetime.datetime.now()
                    .astimezone(self.batcontrol_timezone)
                    .replace(minute=0, second=0, microsecond=0)
                )
                start_time = curr_hour_start + hours_until_range_start
                end_time = start_time + range_duration

                self.high_price_strategies[start_time] = ThermiaStrategySlot(
                    start_time, end_time, heat_modes[i], prices[i], net_consumption[i]
                )

            self.cleanup_high_price_strategies()

            self.already_planned_until = max_timestamp
            self.publish_strategies_to_mqtt()

        else:
            logger.debug(
                "[ThermiaHeatpump] No replanning necessary, already planned until %s",
                self.already_planned_until,
            )
        return

    def adjust_mode_duration(
        self,
        heat_modes: list[str],
        prices: list[float],
        inspected_mode: str,
        downgrade_mode: str,
        max_mode_duration: int,
    ):
        """
        Adjust the duration of a specific heat mode and downgrade
        it if it exceeds the maximum allowed duration.

        Parameters:
        -----------
        heat_modes : list
            List of heat modes for each hour.
        prices : dict
            Dictionary of energy prices for each hour.
        inspected_mode : str
            The heat mode to inspect and potentially downgrade.
        downgrade_mode : str
            The heat mode to downgrade to if the inspected mode exceeds the maximum duration.
        max_mode_duration : int
            The maximum allowed duration for the inspected mode.

        Returns:
        --------
        None
        """
        mode_duration = 0
        start_index = -1

        for h, mode in enumerate(heat_modes):
            if mode == inspected_mode:
                if start_index == -1:
                    start_index = h
                mode_duration += 1

                if mode_duration > max_mode_duration:
                    if prices[start_index] <= prices[h]:
                        heat_modes[start_index] = downgrade_mode
                        logger.debug(
                            "[ThermiaHeatpump] Downgrade %s to %s at +%dh due to duration limit",
                            inspected_mode,
                            downgrade_mode,
                            start_index,
                        )
                        start_index += 1
                    else:
                        heat_modes[h] = downgrade_mode
                        logger.debug(
                            "[ThermiaHeatpump] Downgrade %s to %s at +%dh due to duration limit",
                            inspected_mode,
                            downgrade_mode,
                            h,
                        )
                    mode_duration = 0
                    start_index = -1
            else:
                mode_duration = 0
                start_index = -1

    def apply_mode(self, mode: str, start_index: int, end_index: int):
        """
        Apply a specific mode to the heat pump for a given time range.

        Args:
            mode (str): The mode to be applied to the heat pump.
            start_index (int): The starting hour index from the current time.
            end_index (int): The ending hour index from the current time.

        Returns:
            None

        Logs:
            Logs the mode application with the start and end hour indices.
        """
        logger.debug(
            "[ThermiaHeatpump] Apply Mode %s from +%dh to +%dh",
            mode,
            start_index,
            end_index,
        )

        hours_until_range_start = datetime.timedelta(hours=start_index)
        range_duration = datetime.timedelta(
            hours=end_index - start_index + 1
        )  # add one hour to include the druartion of evenan single 1-hour slot

        curr_hour_start = (
            datetime.datetime.now()
            .astimezone(self.batcontrol_timezone)
            .replace(minute=0, second=0, microsecond=0)
        )
        range_start_time = curr_hour_start + hours_until_range_start
        range_end_time = range_start_time + range_duration

        self.ensure_strategy_for_time_window(range_start_time, range_end_time, mode)

    def ensure_strategy_for_time_window(
        self, start_time: datetime, end_time: datetime, mode: str
    ):
        """
        check whether strategy for certain
        time window is already present or install if it is missing

        Args:
            start_time (datetime): The start time of the high price window.
            end_time (datetime): The end time of the high price window.
            mode (str): The mode of operation for the heat pump during the high price window.
        Raises:
            Error: If the method is not implemented by the subclass.
        """
        ## round to full hour
        start_time = start_time.replace(minute=0, second=0, microsecond=0)
        end_time = end_time.replace(minute=0, second=0, microsecond=0)

        # Adjust start and end times for time zone of heatpump
        tz_name = self.heat_pump.installation_timezone
        start_time = utils.adjust_times_for_timezone(start_time, tz_name)
        end_time = utils.adjust_times_for_timezone(end_time, tz_name)

        duration = end_time - start_time
        logger.info(
            "[ThermiaHeatpump] Planning Strategy [%s] starting at %s, duration: %s",
            mode,
            start_time,
            duration,
        )

        # Check if a strategy already exists for the given start time
        if start_time in self.high_price_handlers:
            existing_strategy = self.high_price_handlers[start_time]
            logger.info(
                "[ThermiaHeatpump] price handler already exists for start time %s: %s",
                start_time,
                existing_strategy,
            )
            return

        schedule = self.install_schedule_in_heatpump(start_time, end_time, mode)
        if schedule:
            high_price_strategy = ThermiaHighPriceHandling(
                start_time, end_time, schedule
            )
            logger.info(
                "[ThermiaHeatpump] Created high price handler: %s", high_price_strategy
            )
            self.high_price_handlers[start_time] = high_price_strategy
        self.cleanup_high_price_handlers()

    def install_schedule_in_heatpump(
        self, start_time: datetime, end_time: datetime, mode: str
    ):
        """
        Installs a schedule in the heat pump based on the provided start time, end time, and mode.

        Args:
            start_time (datetime): The start time for the schedule.
            end_time (datetime): The end time for the schedule.
            mode (str): The mode for the schedule. Can be one of the following:
                - "E": EVU mode
                - "B": Hot water block
                - "R": Reduced heating effect
                - "H": Increased heating effect

        Returns:
            CalendarSchedule: The newly created schedule.

        Raises:
            ValueError: If an unknown mode is provided.
        """

        start_str = start_time.astimezone(self.batcontrol_timezone).strftime("%H:%M")
        end_str = end_time.astimezone(self.batcontrol_timezone).strftime("%H:%M")

        if mode == "E":
            planned_schedule = CalendarSchedule(
                start=start_time, end=end_time, functionId=CAL_FUNCTION_EVU_MODE
            )
            schedule = self.heat_pump.add_new_schedule(planned_schedule)
            logger.debug(
                "[ThermiaHeatpump] Set Heatpump to EVU block from %s to %s",
                start_str,
                end_str,
            )
            return schedule
        elif mode == "B":
            planned_schedule = CalendarSchedule(
                start=start_time, end=end_time, functionId=CAL_FUNCTION_HOT_WATER_BLOCK
            )
            schedule = self.heat_pump.add_new_schedule(planned_schedule)
            logger.debug(
                "[ThermiaHeatpump] Set Heatpump to Hot water BLOCK from %s to %s",
                start_str,
                end_str,
            )
            return schedule
        elif mode == "R":
            planned_schedule = CalendarSchedule(
                start=start_time,
                end=end_time,
                functionId=CAL_FUNCTION_REDUCED_HEATING_EFFECT,
                value=self.reduced_heat_temperature,
            )
            schedule = self.heat_pump.add_new_schedule(planned_schedule)
            logger.debug(
                "[ThermiaHeatpump] Set Heatpump to REDUCED Heating (%s) from %s to %s",
                self.reduced_heat_temperature,
                start_str,
                end_str,
            )
            return schedule
        elif mode == "H":
            planned_schedule = CalendarSchedule(
                start=start_time,
                end=end_time,
                functionId=CAL_FUNCTION_REDUCED_HEATING_EFFECT,
                value=self.increased_heat_temperature,
            )
            schedule = self.heat_pump.add_new_schedule(planned_schedule)
            logger.debug(
                "[ThermiaHeatpump] Set Heatpump to INCREASED Heating (%s) from %s to %s",
                self.increased_heat_temperature,
                start_str,
                end_str,
            )
            return schedule
        elif mode == "W":
            logger.debug(
                "[ThermiaHeatpump] TODO No impl for  Heatpump to Hot Water BOOST from %s to %s",
                start_str,
                end_str,
            )
            return
        elif mode == "N":
            logger.debug(
                "[ThermiaHeatpump] No change in Heatpump mode from %s to %s",
                start_str,
                end_str,
            )
            return
        else:
            logger.error("[ThermiaHeatpump] Unknown mode: %s", mode)
            raise ValueError(f"Unknown mode: {mode}")

    def cleanup_high_price_strategies(self):
        """
        Remove all high price strategies that are no longer valid.

        This method iterates through the high price strategies stored in the
        `self.high_price_strategies` dictionary and removes any strategies
        whose end time is before the current time. The current time is
        adjusted to the heat pump's installation timezone.
        The method logs the following information:
        - The number of high price strategies before cleanup.
        - Each strategy that is removed, including its start and end times.
        - The number of remaining high price strategies after cleanup.

        """
        logger.debug(
            "[ThermiaHeatpump] Cleaning up high price strategies, currently %d strategies",
            len(self.high_price_strategies),
        )
        now = datetime.datetime.now(
            self.batcontrol_timezone
        )  # Make 'now' an aware datetime object in the heat pump's timezone
        now = utils.adjust_times_for_timezone(now, self.heat_pump.installation_timezone)

        strategies_to_remove = []

        for start_time, strategy in self.high_price_strategies.items():
            if strategy.end_time.timestamp() < now.timestamp():
                logger.debug(
                    "[ThermiaHeatpump] Removing high price strategy at %s - %s, "
                    + "because it ends before now: %s",
                    start_time,
                    strategy.end_time,
                    now,
                )
                strategies_to_remove.append(start_time)

        for start_time in strategies_to_remove:
            del self.high_price_strategies[start_time]
            logger.debug(
                "[ThermiaHeatpump] Removed high price strategy for %s", start_time
            )
        logger.debug(
            "[ThermiaHeatpump] Cleanup complete. Remaining strategies: %d",
            len(self.high_price_strategies),
        )

    def cleanup_high_price_handlers(self):
        """
        Remove all high price handlers that are no longer valid.
        """
        now = datetime.datetime.now(
            self.batcontrol_timezone
        )  # Make 'now' an aware datetime object in the heat pump's timezone
        now = utils.adjust_times_for_timezone(now, self.heat_pump.installation_timezone)
        handlers_to_remove = []

        for start_time, handler in self.high_price_handlers.items():
            end_time = handler.end_time
            if end_time.timestamp() < now.timestamp():
                logger.debug(
                    "[ThermiaHeatpump] Removing high price handler for %s-%s , "
                    + "because it ends before now: %s",
                    start_time,
                    end_time,
                    now,
                )
                handlers_to_remove.append(start_time)

        for start_time in handlers_to_remove:
            del self.high_price_handlers[start_time]
            logger.debug(
                "[ThermiaHeatpump] Removed high price handler for %s", start_time
            )
        logger.debug(
            "[ThermiaHeatpump] Cleanup complete. Remaining handlers: %d",
            len(self.high_price_handlers),
        )

    def publish_strategies_to_mqtt(self):
        """
        Publishes high price handlers and strategies to MQTT.

        This method performs the following steps:
        1. Logs the number of handlers and strategies to be published.
        2. Deletes all existing high price handlers from the MQTT topics.
        3. Publishes each high price handler to its respective MQTT topic.
        4. Deletes all existing high price strategies from the MQTT topics.
        5. Publishes each high price strategy to its respective MQTT topic.

        Each handler and strategy is published with its associated details such as
        start time, end time, mode, price, consumption, and handler function ID.

        Note:
            This method assumes that `self.mqtt_client` is an instance of an MQTT client
            that has methods `delete_all_topics` and `generic_publish`.

        Raises:
            AttributeError: If `self.mqtt_client` is None.

        """
        if self.mqtt_client:
            # Delete all existing high price handlers
            logger.debug(
                "[ThermiaHeatpump] publishing strategy values (%d handlers, %d strategies) to MQTT",
                len(self.high_price_handlers),
                len(self.high_price_strategies),
            )

            handlers_prefix = self._get_mqtt_topic() + "handlers/"

            logger.debug(
                "[ThermiaHeatpump] Cleaning up all previously published handlers at %s",
                handlers_prefix,
            )
            self.mqtt_client.delete_all_topics(handlers_prefix)

            for index, (start_time, handler) in enumerate(
                self.high_price_handlers.items()
            ):
                mqtt_handler_topic = handlers_prefix + str(index)
                self.mqtt_client.generic_publish(
                    mqtt_handler_topic,
                    start_time.strftime("%Y-%m-%d_%H:%M")
                    + "-"
                    + handler.end_time.strftime("%H:%M")
                    + "-"
                    + str(handler.schedule.functionId),
                )
                self.mqtt_client.generic_publish(
                    mqtt_handler_topic + "/start_time",
                    handler.start_time.strftime("%Y-%m-%d %H:%M"),
                )
                self.mqtt_client.generic_publish(
                    mqtt_handler_topic + "/end_time",
                    handler.end_time.strftime("%Y-%m-%d %H:%M"),
                )
                self.mqtt_client.generic_publish(
                    mqtt_handler_topic + "/calendar_function_id",
                    handler.schedule.functionId,
                )

            # Delete all existing high price strategies
            strategies_prefix = self._get_mqtt_topic() + "strategies/"
            logger.debug(
                "[ThermiaHeatpump] Cleaning up all previously published strategies at %s",
                strategies_prefix,
            )
            self.mqtt_client.delete_all_topics(strategies_prefix)

            for index, (start_time, strategy) in enumerate(
                self.high_price_strategies.items()
            ):
                high_price_strategy_topic = strategies_prefix + str(index)
                self.mqtt_client.generic_publish(
                    high_price_strategy_topic,
                    start_time.strftime("%Y-%m-%d %H:%M") + ":" + strategy.mode,
                )
                self.mqtt_client.generic_publish(
                    high_price_strategy_topic + "/price", strategy.price
                )
                self.mqtt_client.generic_publish(
                    high_price_strategy_topic + "/consumption", strategy.consumption
                )
                self.mqtt_client.generic_publish(
                    high_price_strategy_topic + "/mode", strategy.mode
                )
                self.mqtt_client.generic_publish(
                    high_price_strategy_topic + "/start_time",
                    strategy.start_time.strftime("%Y-%m-%d %H:%M"),
                )
                self.mqtt_client.generic_publish(
                    high_price_strategy_topic + "/end_time",
                    strategy.end_time.strftime("%Y-%m-%d %H:%M"),
                )
                if strategy.handler:
                    self.mqtt_client.generic_publish(
                        high_price_strategy_topic + "/handler",
                        strategy.handler.schedule.functionId,
                    )

            logger.debug(
                "[ThermiaHeatpump] strategy values (%d handlers, %d strategies) published to MQTT",
                len(self.high_price_handlers),
                len(self.high_price_strategies),
            )

    def shutdown(self):
        """
        Destructor to clean up high price handlers
        and delete corresponding schedules in the Thermia API.
        """
        logger.debug("[ThermiaHeatpump Destructor] Cleaning up high price handlers")
        if self.heat_pump:
            for start_time, handler in self.high_price_handlers.items():
                try:
                    self.heat_pump.delete_schedule(handler.schedule)
                    logger.info(
                        "[ThermiaHeatpump] Deleted schedule for high price handler starting at %s",
                        start_time,
                    )
                except Exception as e:  # pylint: disable=broad-except
                    logger.error(
                        "[ThermiaHeatpump] Failed to delete schedule for handler at %s: %s",
                        start_time,
                        e,
                    )
