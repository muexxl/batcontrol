import logging
import unittest
import datetime
import numpy as np

from batcontrol.logic.default import DefaultLogic
from batcontrol.logic.logic_interface import CalculationInput, CalculationParameters, InverterControlSettings
from batcontrol.logic.common import CommonLogic

logging.basicConfig(level=logging.DEBUG)

class TestDefaultLogic(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.max_capacity = 10000  # 10 kWh
        self.logic = DefaultLogic(timezone=datetime.timezone.utc)
        self.common = CommonLogic.get_instance(
            charge_rate_multiplier=1.1,
            always_allow_discharge_limit=0.80,  # 80%
            max_capacity=self.max_capacity
        )
        # Setup calculation parameters
        self.calculation_parameters = CalculationParameters(
            max_charging_from_grid_limit=0.79,  # 79%
            min_price_difference=0.05,  # 5 cents
            min_price_difference_rel=0.2,  # 20% distance
            max_capacity=self.max_capacity
        )
        self.logic.set_calculation_parameters(self.calculation_parameters)

    def _calculate_battery_values(self, stored_energy, max_capacity) -> tuple:
        """Helper method to calculate stored usable energy and free capacity"""
        # We assume a MIN_SOC of 5% for usable energy
        stored_usable_energy = stored_energy - (max_capacity * 0.05 )
        free_capacity = max_capacity - stored_energy
        soc = (stored_energy / max_capacity) * 100  # Calculate SOC in percentage
        return stored_usable_energy, free_capacity, soc


    def test_init(self):
        """Test initialization of DefaultLogic"""
        self.assertIsNotNone(self.logic)
        self.assertEqual(self.logic.round_price_digits, 4)
        self.assertEqual(self.logic.timezone, datetime.timezone.utc)

    def test_set_calculation_parameters(self):
        """Test setting calculation parameters"""
        self.assertEqual(self.logic.calculation_parameters, self.calculation_parameters)

    def test_calculate_inverter_mode_high_soc(self):
        """Test calculate_inverter_mode with high SOC should allow discharge"""
        #max_capacity = 10000  # 10 kWh
        stored_energy = 9500  #  9,5 kWh
        stored_usable_energy, free_capacity, soc = self._calculate_battery_values(
                                                            stored_energy,
                                                            self.max_capacity )

        consumption = np.array([500, 600, 700])  # Example consumption in W
        production = np.array([0, 0, 0])  # No production for this test

        calc_input = CalculationInput(
            consumption=consumption,
            production=production,
            prices={0: 0.25, 1: 0.30, 2: 0.35},  # Example prices in € per kWh
            stored_energy=stored_energy,
            stored_usable_energy=stored_usable_energy,
            free_capacity=free_capacity,
            soc=soc
        )

        # Call the method under test
        calc_timestamp = datetime.datetime(2025, 6, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(self.logic.calculate(calc_input,calc_timestamp))
        result = self.logic.get_inverter_control_settings()

        # Assert result
        self.assertIsInstance(result, InverterControlSettings)
        self.assertTrue(result.allow_discharge, "Discharge should be allowed due to high SOC")

    def test_calculate_inverter_mode_low_soc(self):
        """Test calculate_inverter_mode with low SOC should not allow discharge"""
        #max_capacity = 10000  # 10 kWh
        stored_energy =  800
        stored_usable_energy, free_capacity, soc = self._calculate_battery_values(
                                                            stored_energy,
                                                            self.max_capacity )

        consumption = np.array([500, 600, 700])  # Example consumption in W
        production = np.array([0, 0, 0])  # No production for this test

        calc_input = CalculationInput(
            consumption=consumption,
            production=production,
            prices={0: 0.30, 1: 0.25, 2: 0.20},  # Current price higher than future
            stored_energy=stored_energy,
            stored_usable_energy=stored_usable_energy,
            free_capacity=free_capacity,
            soc=soc
        )

        # Call the method under test
        calc_timestamp = datetime.datetime(2025, 6, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(self.logic.calculate(calc_input,calc_timestamp))
        result = self.logic.get_inverter_control_settings()

        # Assert result
        self.assertIsInstance(result, InverterControlSettings)
        self.assertFalse(result.allow_discharge, "Discharge should not be allowed due to low SOC")

    def test_discharge_not_allowed_because_reserved(self):
        """Test discharge not allowed because reserved energy is below needed energy"""
        #max_capacity = 10000
        stored_energy =  900
        stored_usable_energy, free_capacity, soc = self._calculate_battery_values(
                                                            stored_energy,
                                                            self.max_capacity )

        consumption = np.array([500, 500, 1000])  # Example consumption in W
        production = np.array([0, 0, 0])  # No production for this test

        calc_input = CalculationInput(
            consumption=consumption,
            production=production,
            prices={0: 0.20, 1: 0.25, 2: 0.30},  # Current price higher than future
            stored_energy=stored_energy,
            stored_usable_energy=stored_usable_energy,
            free_capacity=free_capacity,
            soc=soc
        )

        # Call the method under test
        calc_timestamp = datetime.datetime(2025, 6, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(self.logic.calculate(calc_input,calc_timestamp))
        result = self.logic.get_inverter_control_settings()
        self.assertFalse(result.allow_discharge, "Discharge should not be allowed")


    def test_discharge_allowed_because_highest_price(self):
        """Test discharge allowed because current price is the highest"""
        #max_capacity = 10000
        stored_energy = 2000
        stored_usable_energy, free_capacity, soc = self._calculate_battery_values(
                                                            stored_energy,
                                                            self.max_capacity )

        consumption = np.array([500, 500, 500])  # Example consumption in W
        production = np.array([0, 0, 0])  # No production for

        calc_input = CalculationInput(
            consumption=consumption,
            production=production,
            prices={0: 0.30, 1: 0.25, 2: 0.20},  # Current price higher than future
            stored_energy=stored_energy,
            stored_usable_energy=stored_usable_energy,
            free_capacity=free_capacity,
            soc=soc
        )

        # Call the method under test
        calc_timestamp = datetime.datetime(2025, 6, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(self.logic.calculate(calc_input,calc_timestamp))
        result = self.logic.get_inverter_control_settings()
        self.assertTrue(result.allow_discharge, "Discharge should be allowed")

if __name__ == '__main__':
    unittest.main()
