import unittest
import datetime
import numpy as np

from batcontrol.logic.default_logic import DefaultLogic
from batcontrol.logic.logic_interface import CalculationInput, CalculationParameters, InverterControlSettings

class TestDefaultLogic(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.logic = DefaultLogic(timezone=datetime.timezone.utc)
        
        # Setup calculation parameters
        self.calculation_parameters = CalculationParameters(
            always_allow_discharge_limit=0.8,  # 80%
            max_charging_from_grid_limit=0.9,  # 90%
            min_price_difference=0.05,  # 5 cents
            min_price_difference_rel=0.2,  # 20%
            max_capacity=10000  # 10 kWh
        )
        self.logic.set_calculation_parameters(self.calculation_parameters)
        
    def test_init(self):
        """Test initialization of DefaultLogic"""
        self.assertIsNotNone(self.logic)
        self.assertEqual(self.logic.round_price_digits, 4)
        self.assertEqual(self.logic.charge_rate_multiplier, 1.1)
        self.assertEqual(self.logic.timezone, datetime.timezone.utc)
    
    def test_set_calculation_parameters(self):
        """Test setting calculation parameters"""
        self.assertEqual(self.logic.calculation_parameters, self.calculation_parameters)
    
    def test_is_discharge_always_allowed(self):
        """Test discharge always allowed when SOC is above threshold"""
        # SOC above the threshold
        self.assertTrue(self.logic.is_discharge_always_allowed(8500))  # 8.5 kWh, which is > 8 kWh (80% of 10kWh)
        
        # SOC below the threshold
        self.assertFalse(self.logic.is_discharge_always_allowed(7500))  # 7.5 kWh, which is < 8 kWh
    
    def test_calculate_inverter_mode_high_soc(self):
        """Test calculate_inverter_mode with high SOC should allow discharge"""
        calc_input = CalculationInput(
            net_consumption=np.array([500, 600, 700]),  # Example consumption in W
            prices={0: 0.25, 1: 0.30, 2: 0.35},  # Example prices in € per kWh
            stored_energy=9000,  # 9 kWh
            stored_usable_energy=8500,  # 8.5 kWh
            free_capacity=1000,  # 1 kWh free
            soc=85  # 85% SOC - above discharge limit
        )
        
        # Call the method under test
        calc_timestamp = datetime.datetime(2025, 6, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        result = self.logic.calculate_inverter_mode(calc_input, calc_timestamp)
        
        # Assert result
        self.assertIsInstance(result, InverterControlSettings)
        
    def test_calculate_inverter_mode_low_soc(self):
        """Test calculate_inverter_mode with low SOC should not allow discharge"""
        calc_input = CalculationInput(
            net_consumption=np.array([500, 600, 700]),  # Example consumption in W
            prices={0: 0.30, 1: 0.25, 2: 0.20},  # Current price higher than future
            stored_energy=5000,  # 5 kWh
            stored_usable_energy=4000,  # 4 kWh
            free_capacity=5000,  # 5 kWh free
            soc=50  # 50% SOC - below discharge limit
        )
        
        # Call the method under test
        calc_timestamp = datetime.datetime(2025, 6, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        result = self.logic.calculate_inverter_mode(calc_input, calc_timestamp)
        
        # Assert result
        self.assertIsInstance(result, InverterControlSettings)
        
if __name__ == '__main__':
    unittest.main()
