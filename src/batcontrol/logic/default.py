import logging
import datetime
import numpy as np

from .logic_interface import LogicInterface
from .logic_interface import CalculationParameters, CalculationInput
from .logic_interface import CalculationOutput, InverterControlSettings
from .common import CommonLogic

logger = logging.getLogger(__name__)
rules_logger = logging.getLogger(__name__ + '.rules')

class DefaultLogic(LogicInterface):
    """ Default logic class for Batcontrol. """

    def __init__(self, timezone: datetime.timezone = datetime.timezone.utc):
        self.calculation_parameters = None
        self.calculation_output = None
        self.inverter_control_settings = None
        self.round_price_digits = 4  # Default rounding for prices
        self.soften_price_difference_on_charging = False
        self.soften_price_difference_on_charging_factor = 5.0  # Default factor
        self.timezone = timezone
        self.common = CommonLogic.get_instance()


    def set_round_price_digits(self, digits: int):
        """ Set the number of digits to round prices to """
        self.round_price_digits = digits

    def set_soften_price_differnce_on_charging(self, soften: bool, factor: float = 5):
        """ Set if the price difference should be softened on charging """
        self.soften_price_difference_on_charging = soften
        self.soften_price_difference_on_charging_factor = factor

    def set_calculation_parameters(self, parameters: CalculationParameters):
        """ Set the calculation parameters for the logic """
        self.calculation_parameters = parameters

    def set_timezone(self, timezone: datetime.timezone):
        """ Set the timezone for the logic calculations """
        self.timezone = timezone

    def calculate(self, input_data: CalculationInput, calc_timestamp:datetime = None) -> bool:
        """ Calculate the inverter control settings based on the input data """
        logger.debug("Calculating inverter control settings...")

        if calc_timestamp is None:
            calc_timestamp = datetime.datetime.now().astimezone(self.timezone)

        self.calculation_output = CalculationOutput(
            reserved_energy=0.0,
            required_recharge_energy=0.0,
            min_dynamic_price_difference=0.0
       )


        self.inverter_control_settings = self.calculate_inverter_mode(
            input_data,
            calc_timestamp
        )
        return True

    def get_calculation_output(self) -> CalculationOutput:
        """ Get the calculation output from the last calculation """
        return self.calculation_output

    def get_inverter_control_settings(self) -> InverterControlSettings:
        """ Get the inverter control settings from the last calculation """
        return self.inverter_control_settings

    def calculate_inverter_mode(self, calc_input: CalculationInput,
                                calc_timestamp:datetime = None) -> InverterControlSettings:
        """ Main control logic for battery control """
        # default settings
        inverter_control_settings = InverterControlSettings(
            allow_discharge=False,
            charge_from_grid=False,
            charge_rate=0,
            limit_charge_rate=0
        )

        if self.calculation_output is None:
            logger.error("Calculation output is not set. Please call calculate() first.")
            return None

        net_consumption = calc_input.net_consumption
        prices = calc_input.prices

        if calc_timestamp is None:
            calc_timestamp = datetime.datetime.now().astimezone(self.timezone)

        # ensure availability of data
        max_hour = min(len(net_consumption), len(prices))

        if self.is_discharge_allowed(calc_input, net_consumption, prices, calc_timestamp):
            inverter_control_settings.allow_discharge = True
            return inverter_control_settings
        else:  # discharge not allowed
            rules_logger.debug('Discharging is NOT allowed')
            inverter_control_settings.allow_discharge = False
            charging_limit_percent = self.calculation_parameters.max_charging_from_grid_limit * 100
            required_recharge_energy = self.get_required_required_recharge_energy(
                calc_input,
                net_consumption[:max_hour],
                prices
            )
            is_charging_possible = calc_input.soc < charging_limit_percent

            logger.debug('Charging allowed: %s',
                         is_charging_possible)
            if is_charging_possible:
                rules_logger.debug('Charging is allowed, because SOC is below %.0f%%',
                             charging_limit_percent
                             )
            else:
                rules_logger.debug('Charging is NOT allowed, because SOC is above %.0f%%',
                             charging_limit_percent
                             )

            if required_recharge_energy > 0:
                logger.debug(
                    'Get additional energy via grid: %0.1f Wh',
                    required_recharge_energy
                )
            else:
                rules_logger.debug(
                    'No additional energy required or possible price found.')

            # charge if battery capacity available and more stored energy is required
            if is_charging_possible and required_recharge_energy > 0:
                remaining_time = (
                    60-calc_timestamp.minute)/60
                charge_rate = required_recharge_energy/remaining_time

                charge_rate = self.common.calculate_charge_rate(charge_rate)

                #self.force_charge(charge_rate)
                inverter_control_settings.charge_from_grid = True
                inverter_control_settings.charge_rate = charge_rate
            else:
                # keep current charge level. recharge if solar surplus available
                inverter_control_settings.allow_discharge = False
        #
        return inverter_control_settings

    def is_discharge_allowed(self, calc_input: CalculationInput,
                                    net_consumption: np.ndarray,
                                    prices: dict,
                                    calc_timestamp:datetime = None) -> bool:
        """ Evaluate if the battery is allowed to discharge

            - Check if battery is above always_allow_discharge_limit
            - Calculate required energy to shift toward high price hours
            - Check if discharge is blocked by external source

            return: bool
        """
        if calc_timestamp is None:
            calc_timestamp = datetime.datetime.now().astimezone(self.timezone)

        stored_usable_energy = calc_input.stored_usable_energy

        if self.common.is_discharge_always_allowed_soc(calc_input.soc):
            logger.info(
                "[Rule] Discharge allowed due to always_allow_discharge_limit")
            return True

        current_price = prices[0]

        min_dynamic_price_difference = self.__calculate_min_dynamic_price_difference(
            current_price)

        self.calculation_output.min_dynamic_price_difference = min_dynamic_price_difference

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
        t0 = calc_timestamp
        t1 = t0+dt
        last_hour = t1.astimezone(self.timezone).strftime("%H:59")

        rules_logger.debug(
            'Evaluating next %d hours until %s',
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

        self.calculation_output.reserved_energy = reserved_storage

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

 # %%
    def get_required_required_recharge_energy(self, calc_input: CalculationInput ,
                                              net_consumption: list, prices: dict) -> float:
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
        min_price_difference = self.calculation_parameters.min_price_difference
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
            recharge_energy = required_energy-calc_input.stored_usable_energy
            logger.debug("[Rule] Stored usable Energy: %0.1f , Recharge Energy: %0.1f Wh",
                         calc_input.stored_usable_energy,
                         recharge_energy
                         )
        else:
            recharge_energy = 0

        free_capacity = calc_input.free_capacity

        if recharge_energy <= 0:
            logger.debug(
                "[Rule] No additional energy required, because stored energy is sufficient."
            )
            recharge_energy = 0

        if recharge_energy > free_capacity:
            recharge_energy = free_capacity
            logger.debug(
                "[Rule] Recharge limited by free capacity: %0.1f Wh", recharge_energy)

        self.calculation_output.required_recharge_energy = recharge_energy

        return recharge_energy

    def __calculate_min_dynamic_price_difference(self, price: float) -> float:
        """ Calculate the dynamic limit for the current price """
        return round(
            max(self.calculation_parameters.min_price_difference,
                self.calculation_parameters.min_price_difference_rel * abs(price)),
            self.round_price_digits
        )
