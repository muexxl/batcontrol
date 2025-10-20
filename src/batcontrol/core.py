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
from .provider_manager import get_provider_manager
from .fetching.constants import (
    LOCAL_REFRESH_INTERVAL,
    DEFAULT_MAX_DELAY,
    PARALLEL_FETCH_TIMEOUT
)

ERROR_IGNORE_TIME = 600  # 10 Minutes
EVALUATIONS_EVERY_MINUTES = 3  # Every x minutes on the clock
# Interval between evaluations in seconds
TIME_BETWEEN_EVALUATIONS = EVALUATIONS_EVERY_MINUTES * 60
# Use centralized constants for delays and refresh intervals
DELAY_EVALUATION_BY_SECONDS = DEFAULT_MAX_DELAY  # Use centralized delay constant
TIME_BETWEEN_UTILITY_API_CALLS = LOCAL_REFRESH_INTERVAL  # Use centralized refresh interval


MODE_ALLOW_DISCHARGING = 10
MODE_AVOID_DISCHARGING = 0
MODE_FORCE_CHARGING = -1

logger = logging.getLogger(__name__)


class Batcontrol:
    """ Main class for Batcontrol, handles the logic and control of the battery system """
    general_logic = None  # type: CommonLogic

    def __init__(self, configdict:dict):
        """Initialize Batcontrol with configuration."""
        # Initialize core attributes
        self._initialize_core_attributes()

        # Store config and setup timezone
        self.config = configdict
        self._setup_timezone(configdict)

        # Initialize provider manager and providers
        self._initialize_providers(configdict)

        # Initialize battery control settings
        self._initialize_battery_control(configdict)

        # Setup external APIs (MQTT, EVCC)
        self._setup_external_apis(configdict)

    def _initialize_core_attributes(self):
        """Initialize core instance attributes."""
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

    def _setup_timezone(self, config):
        """Setup timezone configuration."""
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

    def _initialize_providers(self, config):
        """Initialize all data providers (tariff, solar, consumption, inverter)."""
        # Initialize provider manager for shared infrastructure
        self.provider_manager = get_provider_manager()
        logger.info("Using refactored providers with shared infrastructure")

        # Check if parallel fetching should be used
        self.use_parallel_fetching = config.get('use_parallel_fetching', True)  # Default to True
        if self.use_parallel_fetching:
            logger.info("Parallel provider fetching enabled")

        # Create tariff provider with shared infrastructure
        self.dynamic_tariff = tariff_factory.create_tarif_provider(
            config['utility'],
            self.timezone,
            TIME_BETWEEN_UTILITY_API_CALLS,
            DELAY_EVALUATION_BY_SECONDS
        )

        # Create inverter
        self.inverter = inverter_factory.create_inverter(config['inverter'])

        # Create solar forecast provider
        self.pvsettings = config['pvinstallations']
        self.fc_solar = solar_factory.create_solar_provider(
            self.pvsettings,
            self.timezone,
            DELAY_EVALUATION_BY_SECONDS,
            requested_provider=config.get('solar_forecast_provider', 'fcsolarapi')
        )

        # Create consumption forecast provider
        self.fc_consumption = consumption_factory.create_consumption(
            self.timezone,
            config['consumption_forecast']
        )

        # Initialize background fetching for providers
        self.use_background_fetching = config.get('use_background_fetching', True)
        if self.use_background_fetching:
            self._setup_background_fetching()
            logger.info("Asynchronous background fetching enabled")

    def _initialize_battery_control(self, config):
        """Initialize battery control settings and logic."""
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

    def _setup_external_apis(self, config):
        """Setup external API connections (MQTT, EVCC)."""
        # Setup MQTT API
        self.mqtt_api = None
        if config.get('mqtt', None) is not None:
            if config.get('mqtt').get('enabled', False):
                self._setup_mqtt_api(config)

        # Setup EVCC API
        self.evcc_api = None
        if config.get('evcc', None) is not None:
            if config.get('evcc').get('enabled', False):
                self._setup_evcc_api(config)

    def _setup_mqtt_api(self, config):
        """Setup MQTT API connection and callbacks."""
        logger.info('MQTT Connection enabled')
        self.mqtt_api = MqttApi(config.get('mqtt'))
        self.mqtt_api.wait_ready()

        # Register for callbacks
        self.mqtt_api.register_set_callback('mode', self.api_set_mode, int)
        self.mqtt_api.register_set_callback('charge_rate', self.api_set_charge_rate, int)
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

    def _setup_evcc_api(self, config):
        """Setup EVCC API connection and callbacks."""
        logger.info('evcc Connection enabled')
        self.evcc_api = EvccApi(config['evcc'])
        self.evcc_api.register_block_function(self.set_discharge_blocked)
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

    def _setup_background_fetching(self):
        """Setup background fetching for all providers."""
        try:
            # Register providers for background fetching
            self.provider_manager.register_background_fetcher(
                "tariff",
                lambda: self.dynamic_tariff.get_prices(),
                interval_seconds=LOCAL_REFRESH_INTERVAL,  # Use seconds directly
                provider_instance=self.dynamic_tariff
            )

            self.provider_manager.register_background_fetcher(
                "solar",
                lambda: self.fc_solar.get_forecast(),
                interval_seconds=LOCAL_REFRESH_INTERVAL,  # Use seconds directly
                provider_instance=self.fc_solar
            )

            # Start the background fetching
            self.provider_manager.start_background_fetching()
            logger.info("Background fetching started for tariff and solar providers")

        except Exception as e:
            logger.error(f"Failed to setup background fetching: {e}")
            # Fallback to synchronous fetching
            self.use_background_fetching = False
            logger.warning("Falling back to synchronous fetching")

    def shutdown(self):
        """ Shutdown Batcontrol and dependend modules (inverter..) """
        logger.info('Shutting down Batcontrol')

        # Stop background fetching first
        if hasattr(self, 'use_background_fetching') and self.use_background_fetching:
            self.provider_manager.stop_background_fetching()
            logger.info('Background fetching stopped')

        try:
            self.inverter.shutdown()
            del self.inverter
            if self.evcc_api is not None:
                self.evcc_api.shutdown()
                del self.evcc_api

            # Shutdown provider manager if using refactored providers
            if self.provider_manager is not None:
                logger.debug("Shutting down provider manager")
                self.provider_manager.shutdown()
                self.provider_manager = None

        except Exception as e:
            logger.warning(f"Error during shutdown: {e}")

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
        # Reset some values and validate constraints
        self._prepare_run()

        try:
            # Get forecasts from providers
            price_dict, production_forecast, consumption_forecast, fc_period = self._fetch_all_forecasts()

            # Process and prepare data for calculation
            production, consumption, net_consumption, prices = self._prepare_forecast_data(
                price_dict, production_forecast, consumption_forecast, fc_period
            )

            # Skip control logic if API overwrite is active
            if self._handle_api_overwrite():
                return

            # Run calculation and control logic
            self._execute_control_logic(production, consumption, prices)

        except Exception as e:
            logger.warning('Exception occurred during run: %s', e, exc_info=True)
            self.handle_forecast_error()

    def _prepare_run(self):
        """Prepare for run by resetting data and validating constraints."""
        # Reset some values
        self.__reset_run_data()

        # Verify some constrains:
        #   always_allow_discharge needs to be above max_charging from grid.
        #   if not, it will oscillate between discharging and charging.
        always_allow_discharge_limit = self.general_logic.get_always_allow_discharge_limit()
        if always_allow_discharge_limit < self.max_charging_from_grid_limit:
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

    def _fetch_all_forecasts(self):
        """Fetch all forecasts using the configured fetching strategy."""
        if self.use_background_fetching and self.provider_manager is not None:
            return self._fetch_forecasts_async()
        elif self.use_parallel_fetching and self.provider_manager is not None:
            return self._fetch_forecasts_parallel()
        else:
            return self._fetch_forecasts_sequential()

    def _fetch_forecasts_async(self):
        """Fetch forecasts using asynchronous background fetching."""
        logger.debug("Using asynchronous background-fetched data")
        fetch_start_time = time.time()

        # Get data asynchronously with cache-first strategy
        provider_calls = {
            'tariff': lambda: self.dynamic_tariff.get_prices(),
            'solar': lambda: self.fc_solar.get_forecast()
        }

        fetch_results = self.provider_manager.get_provider_data_async(
            provider_calls,
            use_cache_first=True
            # Remove max_cache_age_minutes - let background fetching and TTL handle freshness
        )

        fetch_duration = time.time() - fetch_start_time
        logger.info(f"Asynchronous data access completed in {fetch_duration:.3f}s")

        # Extract results and handle errors
        if isinstance(fetch_results.get('tariff'), Exception):
            raise fetch_results['tariff']
        if isinstance(fetch_results.get('solar'), Exception):
            raise fetch_results['solar']

        price_dict = fetch_results['tariff']
        production_forecast = fetch_results['solar']

        return self._complete_forecast_fetch(price_dict, production_forecast)

    def _fetch_forecasts_parallel(self):
        """Fetch forecasts using parallel fetching."""
        logger.debug("Starting parallel provider fetch")
        fetch_start_time = time.time()

        # Define provider calls for parallel execution
        provider_calls = {
            'prices': lambda: self.dynamic_tariff.get_prices(),
            'production': lambda: self.fc_solar.get_forecast()
        }

        # Execute parallel fetch with timeout
        fetch_results = self.provider_manager.fetch_parallel(
            provider_calls,
            timeout=PARALLEL_FETCH_TIMEOUT,  # Use centralized timeout constant
            fail_fast=False  # Don't fail on single provider error
        )

        fetch_duration = time.time() - fetch_start_time
        logger.info(f"Parallel fetch completed in {fetch_duration:.2f}s")

        # Extract results and handle errors
        if isinstance(fetch_results.get('prices'), Exception):
            raise fetch_results['prices']
        if isinstance(fetch_results.get('production'), Exception):
            raise fetch_results['production']

        price_dict = fetch_results['prices']
        production_forecast = fetch_results['production']

        # Log cache statistics for monitoring
        cache_stats = self.provider_manager.get_cache_manager().get_stats()
        logger.debug(f"Cache statistics: hits={cache_stats.get('hits', 0)}, "
                   f"misses={cache_stats.get('misses', 0)}, "
                   f"hit_rate={cache_stats.get('hit_rate', 0.0):.2%}")

        return self._complete_forecast_fetch(price_dict, production_forecast)

    def _fetch_forecasts_sequential(self):
        """Fetch forecasts using sequential fetching."""
        logger.debug("Starting sequential provider fetch")
        price_dict = self.dynamic_tariff.get_prices()
        production_forecast = self.fc_solar.get_forecast()

        return self._complete_forecast_fetch(price_dict, production_forecast)

    def _complete_forecast_fetch(self, price_dict, production_forecast):
        """Complete the forecast fetch by getting consumption forecast."""
        # harmonize forecast horizon
        fc_period = min(max(price_dict.keys()), max(production_forecast.keys()))
        consumption_forecast = self.fc_consumption.get_forecast(fc_period+1)

        self.reset_forecast_error()
        return price_dict, production_forecast, consumption_forecast, fc_period

    def _prepare_forecast_data(self, price_dict, production_forecast, consumption_forecast, fc_period):
        """Prepare and process forecast data for calculation."""
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

        # Format arrays consistently for logging (suppress scientific notation)
        with np.printoptions(suppress=True):
            logger.debug('Production Forecast: %s', production.round(1))
            logger.debug('Consumption Forecast: %s', consumption.round(1))
            logger.debug('Net Consumption Forecast: %s', net_consumption.round(1))
            logger.debug('Prices: %s', prices.round(self.round_price_digits))

        # Store data for API
        self.__save_run_data(production, consumption, net_consumption, prices)

        # correction for time that has already passed since the start of the current hour
        production[0] *= 1 - datetime.datetime.now().astimezone(self.timezone).minute/60
        consumption[0] *= 1 - datetime.datetime.now().astimezone(self.timezone).minute/60

        return production, consumption, net_consumption, prices

    def _handle_api_overwrite(self):
        """Handle API overwrite mode."""
        if self.api_overwrite:
            logger.info(
                'API Overwrite active. Skipping control logic. '
                'Next evaluation in %.0f seconds',
                TIME_BETWEEN_EVALUATIONS
            )
            self.api_overwrite = False
            return True
        return False

    def _execute_control_logic(self, production, consumption, prices):
        """Execute the main control logic calculation."""
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

        # Update API data
        self.set_reserved_energy(calc_output.reserved_energy)
        if self.mqtt_api is not None:
            self.mqtt_api.publish_min_dynamic_price_diff(
                calc_output.min_dynamic_price_difference)

        # Apply discharge blocking if needed
        if (self.discharge_blocked and
            not self.general_logic.is_discharge_always_allowed_soc(self.get_SOC())):
            logger.debug('Discharge blocked due to external lock')
            inverter_settings.allow_discharge = False

        # Apply calculated settings to inverter
        self._apply_inverter_settings(inverter_settings)

    def _apply_inverter_settings(self, inverter_settings):
        """Apply the calculated settings to the inverter."""
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

    def get_provider_stats(self) -> dict:
        """
        Get comprehensive provider statistics for monitoring.

        Returns:
            dict: Provider statistics including cache, rate limits, threading
        """
        return self.provider_manager.get_global_stats()

    def clear_provider_caches(self):
        """Clear all provider caches via API call."""
        self.provider_manager.clear_all_caches()
        logger.info("API: Cleared all provider caches")

    def reset_provider_rate_limits(self):
        """Reset all provider rate limits via API call."""
        self.provider_manager.reset_rate_limits()
        logger.info("API: Reset all provider rate limits")

    def get_provider_health(self) -> dict:
        """Get provider infrastructure health status."""
        return self.provider_manager.health_check()
