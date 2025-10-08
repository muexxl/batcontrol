#! /usr/bin/env python
""" Batcontrol Core Module

This module is the main entry point for Batcontrol.

It handles the logic and control of the battery system, including:
  - Fetching forecasts for consumption, production, and prices
  - Calculating the optimal charging/discharging strategy
  - Interfacing with the inverter and external APIs (MQTT, evcc)

"""
# %%
from dataclasses import dataclass
import datetime
import time
import os
import logging
import platform

import pytz
import numpy as np
import platform

from .mqtt_api import MqttApi
from .evcc_api import EvccApi

from .logic import Logic as LogicFactory
from .logic import CalculationInput, CalculationParameters
from .logic import CommonLogic

from .dynamictariff import DynamicTariff as tariff_factory
from .inverter import Inverter as inverter_factory
from .forecastsolar import ForecastSolar as solar_factory

from .forecastconsumption import Consumption as consumption_factory

ERROR_IGNORE_TIME = 600  # 10 Minutes
EVALUATIONS_EVERY_MINUTES = 3  # Every x minutes on the clock
DELAY_EVALUATION_BY_SECONDS = 15  # Delay evaluation for x seconds at every trigger
# Interval between evaluations in seconds
TIME_BETWEEN_EVALUATIONS = EVALUATIONS_EVERY_MINUTES * 60
TIME_BETWEEN_UTILITY_API_CALLS = 900  # 15 Minutes


MODE_ALLOW_DISCHARGING = 10
MODE_AVOID_DISCHARGING = 0
MODE_FORCE_CHARGING = -1

logger = logging.getLogger(__name__)


class Batcontrol:
    """ Main class for Batcontrol, handles the logic and control of the battery system """
    general_logic = None  # type: CommonLogic

    def __init__(self, configdict:dict):
        # For API
        self.api_overwrite = False
        # -1 = charge from grid , 0 = avoid discharge , 10 = discharge allowed
        self.last_mode = None
        self.last_charge_rate = 0
        self.last_prices = None
        self.last_consumption = None
        self.last_production = None
        self.last_net_consumption = None

        self.last_SOC = -1              # pylint: disable=invalid-name
        self.last_free_capacity = -1
        self.last_stored_energy = -1
        self.last_reserved_energy = -1
        self.last_max_capacity = -1
        self.last_stored_usable_energy = -1

        self.discharge_blocked = False
        self.discharge_limit = 0

        self.fetched_stored_energy = False
        self.fetched_reserved_energy = False
        self.fetched_max_capacity = False
        self.fetched_soc = False
        self.fetched_stored_usable_energy = False

        self.last_run_time = 0

        self.last_logic_instance = None

        self.config = configdict
        config = configdict

        try:
            tzstring = config['timezone']
            self.timezone = pytz.timezone(tzstring)
        except KeyError:
            raise RuntimeError(
                f"Config Entry in general: timezone {config['timezone']} " +
                "not valid. Try e.g. 'Europe/Berlin'"
            )

        try:
            tz = os.environ['TZ']
            logger.info("Host system time zone is %s", tz)
        except KeyError:
            logger.info(
                "Host system time zone was not set. Setting to %s",
                config['timezone']
            )
            os.environ['TZ'] = config['timezone']

        # time.tzset() is not available on Windows. When handling timezones exclusively using pytz this is fine
        if platform.system() != 'Windows':
            time.tzset()

        self.dynamic_tariff = tariff_factory.create_tarif_provider(
            config['utility'],
            self.timezone,
            TIME_BETWEEN_UTILITY_API_CALLS,
            DELAY_EVALUATION_BY_SECONDS
        )

        self.inverter = inverter_factory.create_inverter(
            config['inverter'])

        self.pvsettings = config['pvinstallations']
        self.fc_solar = solar_factory.create_solar_provider(
            self.pvsettings,
            self.timezone,
            DELAY_EVALUATION_BY_SECONDS,
            requested_provider=config.get(
                'solar_forecast_provider', 'fcsolarapi')
        )

        self.fc_consumption = consumption_factory.create_consumption(
            self.timezone,
            config['consumption_forecast']
        )

        self.batconfig = config['battery_control']
        self.time_at_forecast_error = -1

        self.max_charging_from_grid_limit = self.batconfig.get(
            'max_charging_from_grid_limit', 0.8)
        self.min_price_difference = self.batconfig.get(
            'min_price_difference', 0.05)
        self.min_price_difference_rel = self.batconfig.get(
            'min_price_difference_rel', 0)

        self.round_price_digits = 4

        if self.config.get('battery_control_expert', None) is not None:
            battery_control_expert = self.config.get(
                'battery_control_expert', {})
            self.round_price_digits = battery_control_expert.get(
                'round_price_digits',
                self.round_price_digits)

        self.general_logic = CommonLogic.get_instance(
            charge_rate_multiplier=self.batconfig.get(
                'charge_rate_multiplier', 1.1),
            always_allow_discharge_limit=self.batconfig.get(
            'always_allow_discharge_limit', 0.9),
            max_capacity=self.inverter.get_max_capacity(),
            min_charge_energy=self.batconfig.get('min_recharge_amount', 100.0)
        )

        self.mqtt_api = None
        if config.get('mqtt', None) is not None:
            if config.get('mqtt').get('enabled', False):
                logger.info('MQTT Connection enabled')
                self.mqtt_api = MqttApi(config.get('mqtt'))
                self.mqtt_api.wait_ready()
                # Register for callbacks
                self.mqtt_api.register_set_callback(
                    'mode',
                    self.api_set_mode,
                    int
                )
                self.mqtt_api.register_set_callback(
                    'charge_rate',
                    self.api_set_charge_rate,
                    int
                )
                self.mqtt_api.register_set_callback(
                    'always_allow_discharge_limit',
                    self.api_set_always_allow_discharge_limit,
                    float
                )
                self.mqtt_api.register_set_callback(
                    'max_charging_from_grid_limit',
                    self.api_set_max_charging_from_grid_limit,
                    float
                )
                self.mqtt_api.register_set_callback(
                    'min_price_difference',
                    self.api_set_min_price_difference,
                    float
                )
                self.mqtt_api.register_set_callback(
                    'min_price_difference_rel',
                    self.api_set_min_price_difference_rel,
                    float
                )
                # Inverter Callbacks
                self.inverter.activate_mqtt(self.mqtt_api)

        self.evcc_api = None
        if config.get('evcc', None) is not None:
            if config.get('evcc').get('enabled', False):
                logger.info('evcc Connection enabled')
                self.evcc_api = EvccApi(config['evcc'])
                self.evcc_api.register_block_function(
                    self.set_discharge_blocked)
                self.evcc_api.register_always_allow_discharge_limit(
                    self.set_always_allow_discharge_limit,
                    self.get_always_allow_discharge_limit
                )
                self.evcc_api.register_max_charge_limit(
                    self.set_max_charging_from_grid_limit,
                    self.get_max_charging_from_grid_limit
                )
                self.evcc_api.start()
                self.evcc_api.wait_ready()
                logger.info('evcc Connection ready')

    def shutdown(self):
        """ Shutdown Batcontrol and dependend modules (inverter..) """
        logger.info('Shutting down Batcontrol')
        try:
            self.inverter.shutdown()
            del self.inverter
            if self.evcc_api is not None:
                self.evcc_api.shutdown()
                del self.evcc_api
        except:
            pass

    def reset_forecast_error(self):
        """ Reset the forecast error timer """
        self.time_at_forecast_error = -1

    def handle_forecast_error(self):
        """ Handle forecast errors and fallback to discharging """
        error_ts = time.time()

        # set time_at_forecast_error if it is at the default value of -1
        if self.time_at_forecast_error == -1:
            self.time_at_forecast_error = error_ts

        # get time delta since error
        time_passed = error_ts-self.time_at_forecast_error

        if time_passed < ERROR_IGNORE_TIME:
            # keep current mode
            logger.info("An API Error occured %0.fs ago. "
                        "Keeping inverter mode unchanged.", time_passed)
        else:
            # set default mode
            logger.warning(
                "An API Error occured %0.fs ago. "
                "Setting inverter to default mode (Allow Discharging)",
                time_passed)
            self.allow_discharging()

    def run(self):
        """ Main calculation & control loop """
        # Reset some values
        self.__reset_run_data()

        # Verify some constrains:
        #   always_allow_discharge needs to be above max_charging from grid.
        #   if not, it will oscillate between discharging and charging.
        always_allow_discharge_limit = self.general_logic.get_always_allow_discharge_limit()
        if  always_allow_discharge_limit < self.max_charging_from_grid_limit:
            logger.warning("Always_allow_discharge_limit (%.2f) is"
                           " below max_charging_from_grid_limit (%.2f)",
                           always_allow_discharge_limit,
                           self.max_charging_from_grid_limit
                           )
            self.max_charging_from_grid_limit = always_allow_discharge_limit - 0.01
            logger.warning("Lowering max_charging_from_grid_limit to %.2f",
                           self.max_charging_from_grid_limit)

        # for API
        self.refresh_static_values()
        self.set_discharge_limit(
            self.get_max_capacity() * always_allow_discharge_limit
        )
        self.last_run_time = time.time()

        # get forecasts
        try:
            price_dict = self.dynamic_tariff.get_prices()
            production_forecast = self.fc_solar.get_forecast()
            # harmonize forecast horizon
            fc_period = min(max(price_dict.keys()),
                            max(production_forecast.keys()))
            consumption_forecast = self.fc_consumption.get_forecast(
                fc_period+1)
        except Exception as e:
            logger.warning(
                'Following Exception occurred when trying to get forecasts: %s', e,
                exc_info=True
            )
            self.handle_forecast_error()
            return

        self.reset_forecast_error()

        # initialize arrays
        net_consumption = np.zeros(fc_period+1)
        production = np.zeros(fc_period+1)
        consumption = np.zeros(fc_period+1)
        prices = np.zeros(fc_period+1)

        for h in range(fc_period+1):
            production[h] = production_forecast[h]
            consumption[h] = consumption_forecast[h]
            prices[h] = round(price_dict[h], self.round_price_digits)

        net_consumption = consumption-production

        logger.debug('Production Forecast: %s',
                     np.ndarray.round(production, 1))
        logger.debug('Consumption Forecast: %s',
                     np.ndarray.round(consumption, 1))
        logger.debug('Net Consumption Forecast: %s',
                     np.ndarray.round(net_consumption, 1))
        logger.debug('Prices: %s', np.ndarray.round(
            prices, self.round_price_digits))
        # negative = charging or feed in
        # positive = dis-charging or grid consumption

        # Store data for API
        self.__save_run_data(production, consumption, net_consumption, prices)

        # stop here if api_overwrite is set and reset it
        if self.api_overwrite:
            logger.info(
                'API Overwrite active. Skipping control logic. '
                'Next evaluation in %.0f seconds',
                TIME_BETWEEN_EVALUATIONS
            )
            self.api_overwrite = False
            return

        # correction for time that has already passed since the start of the current hour
        production[0] *= 1 - \
            datetime.datetime.now().astimezone(self.timezone).minute/60
        consumption[0] *= 1 - \
            datetime.datetime.now().astimezone(self.timezone).minute/60

        this_logic_run = LogicFactory.create_logic(self.config, self.timezone)

        # Create input for calculation
        calc_input = CalculationInput(
            production,
            consumption,
            prices,
            self.get_stored_energy(),
            self.get_stored_usable_energy(),
            self.get_free_capacity()
        )
        calc_parameters = CalculationParameters(
            self.max_charging_from_grid_limit,
            self.min_price_difference,
            self.min_price_difference_rel,
            self.get_max_capacity()
        )

        self.last_logic_instance = this_logic_run
        this_logic_run.set_calculation_parameters(calc_parameters)
        # Calculate inverter mode
        logger.debug('Calculating inverter mode...')
        if not this_logic_run.calculate(calc_input):
            logger.error('Calculation failed. Falling back to discharge')
            self.allow_discharging()
            return

        calc_output = this_logic_run.get_calculation_output()
        inverter_settings = this_logic_run.get_inverter_control_settings()

        # for API
        self.set_reserved_energy(calc_output.reserved_energy)
        if self.mqtt_api is not None:
            self.mqtt_api.publish_min_dynamic_price_diff(
                calc_output.min_dynamic_price_difference)

        if self.discharge_blocked and not \
                self.general_logic.is_discharge_always_allowed_soc( self.get_SOC() ):
            # We are blocked by a request outside control loop (evcc)
            # but only if the always_allow_discharge_limit is not reached.
            logger.debug('Discharge blocked due to external lock')
            inverter_settings.allow_discharge = False

        if inverter_settings.allow_discharge:
            self.allow_discharging()
        elif inverter_settings.charge_from_grid:
            self.force_charge(inverter_settings.charge_rate)
        else:
            self.avoid_discharging()

    def __set_charge_rate(self, charge_rate: int):
        """ Set charge rate and publish to mqtt """
        self.last_charge_rate = charge_rate
        if self.mqtt_api is not None:
            self.mqtt_api.publish_charge_rate(charge_rate)

    def __set_mode(self, mode):
        """ Set mode and publish to mqtt """
        self.last_mode = mode
        if self.mqtt_api is not None:
            self.mqtt_api.publish_mode(mode)
        # leaving force charge mode, reset charge rate
        if self.last_charge_rate > 0 and mode != MODE_FORCE_CHARGING:
            self.__set_charge_rate(0)

    def allow_discharging(self):
        """ Allow unlimited discharging of the battery """
        logger.info('Mode: Allow Discharging')
        self.inverter.set_mode_allow_discharge()
        self.__set_mode(MODE_ALLOW_DISCHARGING)

    def avoid_discharging(self):
        """ Avoid discharging the battery """
        logger.info('Mode: Avoid Discharging')
        self.inverter.set_mode_avoid_discharge()
        self.__set_mode(MODE_AVOID_DISCHARGING)

    def force_charge(self, charge_rate=500):
        """ Force the battery to charge with a given rate """
        charge_rate = int(min(charge_rate, self.inverter.max_grid_charge_rate))
        logger.info(
            'Mode: grid charging. Charge rate : %d W', charge_rate)
        self.inverter.set_mode_force_charge(charge_rate)
        self.__set_mode(MODE_FORCE_CHARGING)
        self.__set_charge_rate(charge_rate)

    def __save_run_data(self, production, consumption, net_consumption, prices):
        """ Save data for API """
        self.last_production = production
        self.last_consumption = consumption
        self.last_net_consumption = net_consumption
        self.last_prices = prices
        if self.mqtt_api is not None:
            self.mqtt_api.publish_production(production, self.last_run_time)
            self.mqtt_api.publish_consumption(consumption, self.last_run_time)
            self.mqtt_api.publish_net_consumption(
                net_consumption, self.last_run_time)
            self.mqtt_api.publish_prices(prices, self.last_run_time)

    def __reset_run_data(self):
        """ Reset value Cache """
        self.fetched_soc = False
        self.fetched_max_capacity = False
        self.fetched_stored_energy = False
        self.fetched_reserved_energy = False
        self.fetched_stored_usable_energy = False

    def get_SOC(self) -> float:  # pylint: disable=invalid-name
        """ Returns the SOC in % (0-100) , collects data from inverter """
        if not self.fetched_soc:
            self.last_SOC = self.inverter.get_SOC()
            # self.last_SOC = self.get_stored_energy() / self.get_max_capacity() * 100
            self.fetched_soc = True
        return self.last_SOC

    def get_max_capacity(self) -> float:
        """ Returns capacity Wh of all batteries reduced by MAX_SOC """
        if not self.fetched_max_capacity:
            self.last_max_capacity = self.inverter.get_max_capacity()
            self.fetched_max_capacity = True
            if self.mqtt_api is not None:
                self.mqtt_api.publish_max_energy_capacity(
                    self.last_max_capacity)
        return self.last_max_capacity

    def get_stored_energy(self) -> float:
        """ Returns the stored eneregy in the battery in kWh without
            considering the minimum SOC"""
        if not self.fetched_stored_energy:
            self.set_stored_energy(self.inverter.get_stored_energy())
            self.fetched_stored_energy = True
        return self.last_stored_energy

    def get_stored_usable_energy(self) -> float:
        """ Returns the stored eneregy in the battery in kWh with considering
            the MIN_SOC of inverters. """
        if not self.fetched_stored_usable_energy:
            self.set_stored_usable_energy(
                self.inverter.get_stored_usable_energy())
            self.fetched_stored_usable_energy = True
        return self.last_stored_usable_energy

    def get_free_capacity(self) -> float:
        """ Returns the free capacity in Wh that is usable for (dis)charging """
        self.last_free_capacity = self.inverter.get_free_capacity()
        return self.last_free_capacity

    def set_reserved_energy(self, reserved_energy) -> None:
        """ Set the reserved energy in Wh """
        self.last_reserved_energy = reserved_energy
        if self.mqtt_api is not None:
            self.mqtt_api.publish_reserved_energy_capacity(reserved_energy)

    def get_reserved_energy(self) -> float:
        """ Returns the reserved energy in Wh from last calculation """
        return self.last_reserved_energy

    def set_stored_energy(self, stored_energy) -> None:
        """ Set the stored energy in Wh """
        self.last_stored_energy = stored_energy
        if self.mqtt_api is not None:
            self.mqtt_api.publish_stored_energy_capacity(stored_energy)

    def set_stored_usable_energy(self, stored_usable_energy) -> None:
        """ Saves the stored usable energy for API
            This is the energy that can be used for discharging. This takes
            account of MIN_SOC and MAX_SOC.
        """
        self.last_stored_usable_energy = stored_usable_energy
        if self.mqtt_api is not None:
            self.mqtt_api.publish_stored_usable_energy_capacity(
                stored_usable_energy)

    def set_discharge_limit(self, discharge_limit) -> None:
        """ Sets the always_allow_discharge_limit and publishes it to the API.
            This is the value in Wh.
        """
        self.discharge_limit = discharge_limit
        if self.mqtt_api is not None:
            self.mqtt_api.publish_always_allow_discharge_limit_capacity(
                discharge_limit)

    def set_always_allow_discharge_limit(self, always_allow_discharge_limit: float) -> None:
        """ Set the always allow discharge limit for battery control """
        self.general_logic.set_always_allow_discharge_limit(
            always_allow_discharge_limit)
        if self.mqtt_api is not None:
            self.mqtt_api.publish_always_allow_discharge_limit(
                always_allow_discharge_limit)

    def get_always_allow_discharge_limit(self) -> float:
        """ Get the always allow discharge limit for battery control """
        return self.general_logic.get_always_allow_discharge_limit()

    def set_max_charging_from_grid_limit(self, limit: float) -> None:
        """ Set the max charging from grid limit for battery control """
        # tbh , we should raise an exception here.
        if limit > self.get_always_allow_discharge_limit():
            logger.error(
                'Max charging from grid limit %.2f is '
                'above always_allow_discharge_limit %.2f',
                limit,
                self.get_always_allow_discharge_limit()
            )
            return
        self.max_charging_from_grid_limit = limit
        if self.mqtt_api is not None:
            self.mqtt_api.publish_max_charging_from_grid_limit(limit)

    def get_max_charging_from_grid_limit(self) -> float:
        """ Get the max charging from grid limit for battery control """
        return self.max_charging_from_grid_limit

    def set_discharge_blocked(self, discharge_blocked) -> None:
        """ Avoid discharging if an external block is received,
            but take care of the always_allow_discharge_limit.

            If block is removed, the next calculation cycle will
            decide what to do.
        """
        if discharge_blocked == self.discharge_blocked:
            return
        logger.info('Discharge block: %s', {discharge_blocked})
        if self.mqtt_api is not None:
            self.mqtt_api.publish_discharge_blocked(discharge_blocked)
        self.discharge_blocked = discharge_blocked

        if not self.general_logic.is_discharge_always_allowed_soc(
                        self.get_SOC()
                        ):
                self.avoid_discharging()


    def refresh_static_values(self) -> None:
        """ Refresh static and some dynamic values for API.
            Collected data is stored, that it is not fetched again.
        """
        if self.mqtt_api is not None:
            self.mqtt_api.publish_SOC(self.get_SOC())
            self.mqtt_api.publish_stored_energy_capacity(
                self.get_stored_energy())
            #
            self.mqtt_api.publish_always_allow_discharge_limit(
                self.get_always_allow_discharge_limit())
            self.mqtt_api.publish_max_charging_from_grid_limit(
                self.max_charging_from_grid_limit)
            #
            self.mqtt_api.publish_min_price_difference(
                self.min_price_difference)
            self.mqtt_api.publish_min_price_difference_rel(
                self.min_price_difference_rel)
            #
            self.mqtt_api.publish_evaluation_intervall(
                TIME_BETWEEN_EVALUATIONS)
            self.mqtt_api.publish_last_evaluation_time(self.last_run_time)
            #
            self.mqtt_api.publish_discharge_blocked(self.discharge_blocked)
            # Trigger Inverter
            self.inverter.refresh_api_values()

    def api_set_mode(self, mode: int):
        """ Log and change config run mode of inverter(s) from external call """
        # Check if mode is valid
        if mode not in [MODE_FORCE_CHARGING, MODE_AVOID_DISCHARGING, MODE_ALLOW_DISCHARGING]:
            logger.warning('API: Invalid mode %s', mode)
            return

        logger.info('API: Setting mode to %s', mode)
        self.api_overwrite = True

        if mode != self.last_mode:
            if mode == MODE_FORCE_CHARGING:
                self.force_charge()
            elif mode == MODE_AVOID_DISCHARGING:
                self.avoid_discharging()
            elif mode == MODE_ALLOW_DISCHARGING:
                self.allow_discharging()

    def api_set_charge_rate(self, charge_rate: int):
        """ Log and change config charge_rate and activate charging."""
        if charge_rate < 0:
            logger.warning(
                'API: Invalid charge rate %d W', charge_rate)
            return
        logger.info('API: Setting charge rate to %d W',  charge_rate)
        self.api_overwrite = True
        if charge_rate != self.last_charge_rate:
            self.force_charge(charge_rate)

    def api_set_always_allow_discharge_limit(self, limit: float):
        """ Set always allow discharge limit for battery control via external API request.
            The change is temporary and will not be written to the config file.
        """
        if limit < 0 or limit > 1:
            logger.warning(
                'API: Invalid always allow discharge limit %.2f', limit)
            return
        logger.info(
            'API: Setting always allow discharge limit to %.2f', limit)
        self.set_always_allow_discharge_limit(limit)

    def api_set_max_charging_from_grid_limit(self, limit: float):
        """ Set max charging from grid limit for battery control via external API request.
            The change is temporary and will not be written to the config file.
        """
        if limit < 0 or limit > 1:
            logger.warning(
                'API: Invalid max charging from grid limit %.2f', limit)
            return
        logger.info(
            'API: Setting max charging from grid limit to %.2f', limit)
        self.set_max_charging_from_grid_limit(limit)

    def api_set_min_price_difference(self, min_price_difference: float):
        """ Set min price difference for battery control via external API request.
            The change is temporary and will not be written to the config file.
        """
        if min_price_difference < 0:
            logger.warning(
                'API: Invalid min price difference %.3f', min_price_difference)
            return
        logger.info(
            'API: Setting min price difference to %.3f', min_price_difference)
        self.min_price_difference = min_price_difference

    def api_set_min_price_difference_rel(self, min_price_difference_rel: float):
        """ Log and change config min_price_difference_rel from external call """
        if min_price_difference_rel < 0:
            logger.warning(
                'API: Invalid min price rel difference %.3f', min_price_difference_rel)
            return
        logger.info(
            'API: Setting min price rel difference to %.3f', min_price_difference_rel)
        self.min_price_difference_rel = min_price_difference_rel
