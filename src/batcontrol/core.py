#! /usr/bin/env python
# %%
import sys
import datetime
import time
import os
import logging
import platform

import yaml
import pytz
import numpy as np

from .mqtt_api import MqttApi
from .evcc_api import EvccApi

from .dynamictariff import DynamicTariff as tariff_factory
from .inverter import Inverter as inverter_factory
from .logfilelimiter import LogFileLimiter

from .forecastsolar import ForecastSolar as solar_factory

from .forecastconsumption import Consumption as consumption_factory


LOGFILE_ENABLED_DEFAULT = True
LOGFILE = "logs/batcontrol.log"

ERROR_IGNORE_TIME = 600  # 10 Minutes
EVALUATIONS_EVERY_MINUTES = 3  # Every x minutes on the clock
DELAY_EVALUATION_BY_SECONDS = 15  # Delay evaluation for x seconds at every trigger
# Interval between evaluations in seconds
TIME_BETWEEN_EVALUATIONS = EVALUATIONS_EVERY_MINUTES * 60
TIME_BETWEEN_UTILITY_API_CALLS = 900  # 15 Minutes
# Minimum charge rate to controlling loops between charging and
#   self discharge.
# 500W is Fronius' internal value for forced recharge.
MIN_CHARGE_RATE = 500


MODE_ALLOW_DISCHARGING = 10
MODE_AVOID_DISCHARGING = 0
MODE_FORCE_CHARGING = -1

loglevel = logging.DEBUG
logger = logging.getLogger('__main__')
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                              "%Y-%m-%d %H:%M:%S")

streamhandler = logging.StreamHandler(sys.stdout)
streamhandler.setFormatter(formatter)

logger.addHandler(streamhandler)

logger.setLevel(loglevel)

logger.info('[Main] Starting Batcontrol')


class Batcontrol:
    def __init__(self, configfile: str):
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

        self.logfile = LOGFILE
        self.logfile_enabled = True
        self.logfilelimiter = None

        self.load_config(configfile)
        config = self.config

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
            logger.info("[Batcontrol] host system time zone is %s", tz)
        except KeyError:
            logger.info(
                "[Batcontrol] host system time zone was not set. Setting to %s",
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

        self.always_allow_discharge_limit = self.batconfig.get(
            'always_allow_discharge_limit', 0.9)
        self.max_charging_from_grid_limit = self.batconfig.get(
            'max_charging_from_grid_limit', 0.8)
        self.min_price_difference = self.batconfig.get(
            'min_price_difference', 0.05)
        self.min_price_difference_rel = self.batconfig.get(
            'min_price_difference_rel', 0)

        self.charge_rate_multiplier = 1.1
        self.soften_price_difference_on_charging = False
        self.soften_price_difference_on_charging_factor = 5
        self.round_price_digits = 4

        if self.config.get('battery_control_expert', None) is not None:
            battery_control_expert = self.config.get(
                'battery_control_expert', {})
            self.soften_price_difference_on_charging = battery_control_expert.get(
                'soften_price_difference_on_charging',
                self.soften_price_difference_on_charging)

            self.soften_price_difference_on_charging_factor = battery_control_expert.get(
                'soften_price_difference_on_charging_factor',
                self.soften_price_difference_on_charging_factor)
            self.round_price_digits = battery_control_expert.get(
                'round_price_digits',
                self.round_price_digits)
            self.charge_rate_multiplier = battery_control_expert.get(
                'charge_rate_multiplier',
                self.charge_rate_multiplier)

        self.mqtt_api = None
        if config.get('mqtt', None) is not None:
            if config.get('mqtt').get('enabled', False):
                logger.info('[Main] MQTT Connection enabled')
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
                logger.info('[Main] evcc Connection enabled')
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
                logger.info('[Main] evcc Connection ready')

    def shutdown(self):
        """ Shutdown Batcontrol and dependend modules (inverter..) """
        logger.info('[Main] Shutting down Batcontrol')
        try:
            self.inverter.shutdown()
            del self.inverter
            if self.evcc_api is not None:
                self.evcc_api.shutdown()
                del self.evcc_api
        except:
            pass

    def load_config(self, configfile):
        """ Load the configuration file and check for validity.
            This maps some config entries for compatibility reasons.
         """
        if not os.path.isfile(configfile):
            raise RuntimeError(f'Configfile {configfile} not found')

        with open(configfile, 'r', encoding='UTF-8') as f:
            config_str = f.read()

        config = yaml.safe_load(config_str)

        if config['pvinstallations']:
            pass
        else:
            raise RuntimeError('No PV Installation found')

        global loglevel
        loglevel = config.get('loglevel', 'info')

        if loglevel == 'debug':
            logger.setLevel(logging.DEBUG)
        elif loglevel == 'warning':
            logger.setLevel(logging.WARNING)
        elif loglevel == 'error':
            logger.setLevel(logging.ERROR)
        elif loglevel == 'info':
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.INFO)
            logger.info(
                '[BATCtrl] Provided loglevel "%s" not valid. Defaulting to loglevel "info"',
                loglevel
            )

        log_is_enabled = config.get('logfile_enabled', LOGFILE_ENABLED_DEFAULT)
        if log_is_enabled:
            self.setup_logfile(config)
        else:
            self.logfile_enabled = False
            logger.info(
                "[Main] Logfile disabled in config. Proceeding without logfile"
            )

        self.config = config

    def setup_logfile(self, config):
        """ Setup the logfile and correpsonding handlers """

        if config.get('max_logfile_size', None) is not None:
            if isinstance(config['max_logfile_size'], int):
                pass
            else:
                raise RuntimeError(
                    f"Config Entry in general: max_logfile_size {config['max_logfile_size']}" +
                    " not valid. Only integer values allowed"
                )
        # default to unlimited filesize
        else:
            config['max_logfile_size'] = -1

        if 'logfile_path' in config.keys():
            self.logfile = config.get('logfile_path')
        else:
            logger.info(
                "[Main] No logfile path provided. Proceeding with default logfile path: %s",
                self.logfile
            )

        if config.get('max_logfile_size') > 0:
            self.logfilelimiter = LogFileLimiter(
                self.logfile, config.get('max_logfile_size'))

        # is the path valid and writable?
        if not os.path.isdir(os.path.dirname(self.logfile)):
            raise RuntimeError(
                f"Logfile path {os.path.dirname(self.logfile)} not found"
            )
        if not os.access(os.path.dirname(self.logfile), os.W_OK):
            raise RuntimeError(
                f"Logfile path {os.path.dirname(self.logfile)} not writable"
            )

        filehandler = logging.FileHandler(self.logfile)
        filehandler.setFormatter(formatter)
        logger.addHandler(filehandler)

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
            logger.info("[BatCtrl] An API Error occured %0.fs ago. "
                        "Keeping inverter mode unchanged.", time_passed)
        else:
            # set default mode
            logger.warning(
                "[BatCtrl] An API Error occured %0.fs ago. "
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
        if self.always_allow_discharge_limit < self.max_charging_from_grid_limit:
            logger.warning("[BatCtrl] always_allow_discharge_limit (%.2f) is"
                           " below max_charging_from_grid_limit (%.2f)",
                           self.always_allow_discharge_limit,
                           self.max_charging_from_grid_limit
                           )
            self.max_charging_from_grid_limit = self.always_allow_discharge_limit - 0.01
            logger.warning("[BatCtrl] Lowering max_charging_from_grid_limit to %.2f",
                           self.max_charging_from_grid_limit)

        # for API
        self.refresh_static_values()
        self.set_discharge_limit(
            self.get_max_capacity() * self.always_allow_discharge_limit
        )
        self.last_run_time = time.time()

        # prune log file if file is too large
        if self.logfilelimiter is not None and self.logfile_enabled:
            self.logfilelimiter.run()

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
                '[BatCtrl] Following Exception occurred when trying to get forecasts: %s', e,
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
        logger.debug('[BatCTRL] Production FCST: %s',
                     np.ndarray.round(production, 1))
        logger.debug('[BatCTRL] Consumption FCST: %s',
                     np.ndarray.round(consumption, 1))
        logger.debug('[BatCTRL] Net Consumption FCST: %s',
                     np.ndarray.round(net_consumption, 1))
        logger.debug('[BatCTRL] Prices: %s', np.ndarray.round(
            prices, self.round_price_digits))
        # negative = charging or feed in
        # positive = dis-charging or grid consumption

        # Store data for API
        self.__save_run_data(production, consumption, net_consumption, prices)

        # stop here if api_overwrite is set and reset it
        if self.api_overwrite:
            logger.info(
                '[BatCTRL] API Overwrite active. Skipping control logic. '
                'Next evaluation in %.0f seconds',
                TIME_BETWEEN_EVALUATIONS
            )
            self.api_overwrite = False
            return

        # correction for time that has already passed since the start of the current hour
        net_consumption[0] *= 1 - \
            datetime.datetime.now().astimezone(self.timezone).minute/60

        self.set_wr_parameters(net_consumption, price_dict)

        # %%
    def set_wr_parameters(self, net_consumption: np.ndarray, prices: dict):
        """ Main control logic for battery control """
        # ensure availability of data
        max_hour = min(len(net_consumption), len(prices))

        if self.is_discharge_allowed(net_consumption, prices):
            self.allow_discharging()
        else:  # discharge not allowed
            logger.debug('[Rule] Discharging is NOT allowed')
            charging_limit_percent = self.max_charging_from_grid_limit * 100
            required_recharge_energy = self.get_required_required_recharge_energy(
                net_consumption[:max_hour],
                prices
            )
            is_charging_possible = self.get_SOC() < charging_limit_percent

            logger.debug('[BatCTRL] Charging allowed: %s',
                         is_charging_possible)
            if is_charging_possible:
                logger.debug('[Rule] Charging is allowed, because SOC is below %.0f%%',
                             charging_limit_percent
                             )
            else:
                logger.debug('[Rule] Charging is NOT allowed, because SOC is above %.0f%%',
                             charging_limit_percent
                             )

            if required_recharge_energy > 0:
                logger.debug(
                    '[BatCTRL] Get additional energy via grid: %0.1f Wh',
                    required_recharge_energy
                )
            else:
                logger.debug(
                    '[Rule] No additional energy required or possible price found.')

            # charge if battery capacity available and more stored energy is required
            if is_charging_possible and required_recharge_energy > 0:
                remaining_time = (
                    60-datetime.datetime.now().astimezone(self.timezone).minute)/60
                charge_rate = required_recharge_energy/remaining_time
                # apply multiplier for charge inefficiency
                charge_rate *= self.charge_rate_multiplier

                if charge_rate < MIN_CHARGE_RATE:
                    logger.debug("[Rule] Charge rate increased to minimum %d W from %f.1 W",
                                 MIN_CHARGE_RATE,
                                 charge_rate
                                 )
                    charge_rate = MIN_CHARGE_RATE

                self.force_charge(charge_rate)

            else:  # keep current charge level. recharge if solar surplus available
                self.avoid_discharging()

    # %%
    def get_required_required_recharge_energy(self, net_consumption: list, prices: dict) -> float:
        """ Calculate the required energy to shift toward high price hours.

            If a recharge price window is detected, the energy required to
            recharge the battery to the next high price hours is calculated.

            return: float (Energy in Wh)
         """
        current_price = prices[0]
        max_hour = len(net_consumption)
        consumption = np.array(net_consumption)
        consumption[consumption < 0] = 0

        production = -np.array(net_consumption)
        production[production < 0] = 0
        min_price_difference = self.min_price_difference
        min_dynamic_price_difference = self.__calculate_min_dynamic_price_difference(
            current_price)

        # evaluation period until price is first time lower then current price
        for h in range(1, max_hour):
            future_price = prices[h]
            found_lower_price = False
            # Soften the price difference to avoid too early charging
            if self.soften_price_difference_on_charging:
                modified_price = current_price-min_price_difference / \
                    self.soften_price_difference_on_charging_factor
                found_lower_price = future_price <= modified_price
            else:
                found_lower_price = future_price <= current_price

            if found_lower_price:
                max_hour = h
                break

        # get high price hours
        high_price_hours = []
        for h in range(max_hour):
            future_price = prices[h]
            if future_price > current_price+min_dynamic_price_difference:
                high_price_hours.append(h)

        # start with nearest hour
        high_price_hours.sort()
        required_energy = 0
        for high_price_hour in high_price_hours:
            energy_to_shift = consumption[high_price_hour]

            # correct energy to shift with potential production
            # start with nearest hour
            for hour in range(1, high_price_hour):
                if production[hour] == 0:
                    continue
                if production[hour] >= energy_to_shift:
                    production[hour] -= energy_to_shift
                    energy_to_shift = 0
                else:
                    energy_to_shift -= production[hour]
                    production[hour] = 0
            # add_remaining energy to shift to recharge amount
            required_energy += energy_to_shift

        if required_energy > 0:
            logger.debug("[Rule] Required Energy: %0.1f Wh is based on next 'high price' hours %s",
                         required_energy,
                         high_price_hours
                         )
            recharge_energy = required_energy-self.get_stored_usable_energy()
            logger.debug("[Rule] Stored usable Energy: %0.1f , Recharge Energy: %0.1f Wh",
                         self.get_stored_usable_energy(),
                         recharge_energy
                         )
        else:
            recharge_energy = 0

        free_capacity = self.get_free_capacity()

        if recharge_energy <= 0:
            logger.debug(
                "[Rule] No additional energy required, because stored energy is sufficient."
            )
            recharge_energy = 0

        if recharge_energy > free_capacity:
            recharge_energy = free_capacity
            logger.debug(
                "[Rule] Recharge limited by free capacity: %0.1f Wh", recharge_energy)

        return recharge_energy

    def __is_above_always_allow_discharge_limit(self) -> bool:
        """ Evaluate if the battery is allowed to discharge always
            return: bool
        """
        stored_energy = self.get_stored_energy()
        discharge_limit = self.get_max_capacity() * self.always_allow_discharge_limit
        if stored_energy > discharge_limit:
            logger.debug(
                '[BatCTRL] Battery with %d Wh above discharge limit %d Wh',
                stored_energy,
                discharge_limit
            )
            return True
        return False
# %%

    def is_discharge_allowed(self, net_consumption: np.ndarray, prices: dict) -> bool:
        """ Evaluate if the battery is allowed to discharge

            - Check if battery is above always_allow_discharge_limit
            - Calculate required energy to shift toward high price hours
            - Check if discharge is blocked by external source

            return: bool
        """
        self.get_stored_energy()
        stored_usable_energy = self.get_stored_usable_energy()

        if self.__is_above_always_allow_discharge_limit():
            logger.info(
                "[Rule] Discharge allowed due to always_allow_discharge_limit")
            return True

        current_price = prices[0]

        min_dynamic_price_difference = self.__calculate_min_dynamic_price_difference(
            current_price)
        if self.mqtt_api is not None:
            self.mqtt_api.publish_min_dynamic_price_diff(
                min_dynamic_price_difference)

        max_hour = len(net_consumption)
        # relevant time range : until next recharge possibility
        for h in range(1, max_hour):
            future_price = prices[h]
            if future_price <= current_price-min_dynamic_price_difference:
                max_hour = h
                logger.debug(
                    "[Rule] Recharge possible in %d hours, limiting evaluation window.",
                    h)
                logger.debug(
                    "[Rule] Future price: %.3f < Current price: %.3f - dyn_price_diff. %.3f ",
                    future_price,
                    current_price,
                    min_dynamic_price_difference
                )
                break
        dt = datetime.timedelta(hours=max_hour-1)
        t0 = datetime.datetime.now()
        t1 = t0+dt
        last_hour = t1.astimezone(self.timezone).strftime("%H:59")

        logger.debug(
            '[Rule] Evaluating next %d hours until %s',
            max_hour,
            last_hour
        )
        # distribute remaining energy
        consumption = np.array(net_consumption)
        consumption[consumption < 0] = 0

        production = -np.array(net_consumption)
        production[production < 0] = 0

        # get hours with higher price
        higher_price_hours = []
        for h in range(max_hour):
            future_price = prices[h]
            # !!! different formula compared to detect relevant hours
            if future_price > current_price:
                higher_price_hours.append(h)

        higher_price_hours.sort()
        higher_price_hours.reverse()

        reserved_storage = 0
        for higher_price_hour in higher_price_hours:
            if consumption[higher_price_hour] == 0:
                continue
            required_energy = consumption[higher_price_hour]

            # correct reserved_storage with potential production
            # start with latest hour
            for hour in list(range(higher_price_hour))[::-1]:
                if production[hour] == 0:
                    continue
                if production[hour] >= required_energy:
                    production[hour] -= required_energy
                    required_energy = 0
                    break
                else:
                    required_energy -= production[hour]
                    production[hour] = 0
            # add_remaining required_energy to reserved_storage
            reserved_storage += required_energy

        if len(higher_price_hours) > 0:
            # This message is somehow confusing, because we are working with an
            # hour offset "the next 2 hours", but people may read "2 o'clock".
            logger.debug("[Rule] Reserved Energy will be used in the next hours: %s",
                         higher_price_hours[::-1])
            logger.debug(
                "[Rule] Reserved Energy: %0.1f Wh. Usable in Battery: %0.1f Wh",
                reserved_storage,
                stored_usable_energy
            )
        else:
            logger.debug("[Rule] No reserved energy required, because no "
                         "'high price' hours in evaluation window.")

        # for API
        self.set_reserved_energy(reserved_storage)

        if self.discharge_blocked:
            logger.debug(
                '[BatCTRL] Discharge blocked due to external lock'
            )
            return False

        if stored_usable_energy > reserved_storage:
            # allow discharging
            logger.debug(
                "[Rule] Discharge allowed. Stored usable energy %0.1f Wh >"
                " Reserved energy %0.1f Wh",
                stored_usable_energy,
                reserved_storage
            )
            return True

        # forbid discharging
        logger.debug(
            "[Rule] Discharge forbidden. Stored usable energy %0.1f Wh <= Reserved energy %0.1f Wh",
            stored_usable_energy,
            reserved_storage
        )

        return False

    def __calculate_min_dynamic_price_difference(self, price: float) -> float:
        """ Calculate the dynamic limit for the current price """
        return round(
            max(self.min_price_difference,
                self.min_price_difference_rel * abs(price)),
            self.round_price_digits
        )

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
        logger.info('[BatCTRL] Mode: Allow Discharging')
        self.inverter.set_mode_allow_discharge()
        self.__set_mode(MODE_ALLOW_DISCHARGING)

    def avoid_discharging(self):
        """ Avoid discharging the battery """
        logger.info('[BatCTRL] Mode: Avoid Discharging')
        self.inverter.set_mode_avoid_discharge()
        self.__set_mode(MODE_AVOID_DISCHARGING)

    def force_charge(self, charge_rate=500):
        """ Force the battery to charge with a given rate """
        charge_rate = int(min(charge_rate, self.inverter.max_grid_charge_rate))
        logger.info(
            '[BatCTRL] Mode: grid charging. Charge rate : %d W', charge_rate)
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
        self.always_allow_discharge_limit = always_allow_discharge_limit
        if self.mqtt_api is not None:
            self.mqtt_api.publish_always_allow_discharge_limit(
                always_allow_discharge_limit)

    def get_always_allow_discharge_limit(self) -> float:
        """ Get the always allow discharge limit for battery control """
        return self.always_allow_discharge_limit

    def set_max_charging_from_grid_limit(self, limit: float) -> None:
        """ Set the max charging from grid limit for battery control """
        # tbh , we should raise an exception here.
        if limit > self.get_always_allow_discharge_limit():
            logger.error(
                '[BatCtrl] Max charging from grid limit %.2f is '
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
        logger.info('[BatCTRL] Discharge block: %s', {discharge_blocked})
        if self.mqtt_api is not None:
            self.mqtt_api.publish_discharge_blocked(discharge_blocked)
        self.discharge_blocked = discharge_blocked

        if not self.__is_above_always_allow_discharge_limit():
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
                self.always_allow_discharge_limit)
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
            logger.warning('[BatCtrl] API: Invalid mode %s', mode)
            return

        logger.info('[BatCtrl] API: Setting mode to %s', mode)
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
                '[BatCtrl] API: Invalid charge rate %d W', charge_rate)
            return
        logger.info('[BatCtrl] API: Setting charge rate to %d W',  charge_rate)
        self.api_overwrite = True
        if charge_rate != self.last_charge_rate:
            self.force_charge(charge_rate)

    def api_set_always_allow_discharge_limit(self, limit: float):
        """ Set always allow discharge limit for battery control via external API request.
            The change is temporary and will not be written to the config file.
        """
        if limit < 0 or limit > 1:
            logger.warning(
                '[BatCtrl] API: Invalid always allow discharge limit %.2f', limit)
            return
        logger.info(
            '[BatCtrl] API: Setting always allow discharge limit to %.2f', limit)
        self.set_always_allow_discharge_limit(limit)

    def api_set_max_charging_from_grid_limit(self, limit: float):
        """ Set max charging from grid limit for battery control via external API request.
            The change is temporary and will not be written to the config file.
        """
        if limit < 0 or limit > 1:
            logger.warning(
                '[BatCtrl] API: Invalid max charging from grid limit %.2f', limit)
            return
        logger.info(
            '[BatCtrl] API: Setting max charging from grid limit to %.2f', limit)
        self.set_max_charging_from_grid_limit(limit)

    def api_set_min_price_difference(self, min_price_difference: float):
        """ Set min price difference for battery control via external API request.
            The change is temporary and will not be written to the config file.
        """
        if min_price_difference < 0:
            logger.warning(
                '[BatCtrl] API: Invalid min price difference %.3f', min_price_difference)
            return
        logger.info(
            '[BatCtrl] API: Setting min price difference to %.3f', min_price_difference)
        self.min_price_difference = min_price_difference

    def api_set_min_price_difference_rel(self, min_price_difference_rel: float):
        """ Log and change config min_price_difference_rel from external call """
        if min_price_difference_rel < 0:
            logger.warning(
                '[BatCtrl] API: Invalid min price rel difference %.3f', min_price_difference_rel)
            return
        logger.info(
            '[BatCtrl] API: Setting min price rel difference to %.3f', min_price_difference_rel)
        self.min_price_difference_rel = min_price_difference_rel
