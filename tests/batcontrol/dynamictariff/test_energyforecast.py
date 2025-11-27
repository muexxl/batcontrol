import unittest
import unittest.mock
import datetime
import pytz
from unittest.mock import patch
from batcontrol.dynamictariff.energyforecast import Energyforecast


class TestEnergyforecast(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.timezone = pytz.timezone('Europe/Berlin')
        self.token = 'demo_token'
        self.vat = 0.20
        self.fees = 0.015
        self.markup = 0.03

    def test_basic_price_extraction(self):
        """Test basic price extraction from API response"""
        energyforecast = Energyforecast(self.timezone, self.token)
        energyforecast.set_price_parameters(self.vat, self.fees, self.markup)

        # Mock raw data - store as dict with 'data' key
        raw_data = {
            'data': [
                {
                    'start': '2024-06-20T10:00:00+02:00',
                    'end': '2024-06-20T11:00:00+02:00',
                    'price': 0.20,
                    'price_origin': 'test'
                },
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'end': '2024-06-20T12:00:00+02:00',
                    'price': 0.25,
                    'price_origin': 'test'
                },
                {
                    'start': '2024-06-20T12:00:00+02:00',
                    'end': '2024-06-20T13:00:00+02:00',
                    'price': 0.22,
                    'price_origin': 'test'
                }
            ]
        }
        energyforecast.store_raw_data(raw_data)

        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.energyforecast.datetime') as mock_datetime:
            # Set current time to 10:00 so all prices are in the future
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = energyforecast._get_prices_native()

        # Verify prices are calculated with fees, markup and vat
        # Formula: (price * (1 + markup) + fees) * (1 + vat)
        expected_price_0 = (0.20 * (1 + 0.03) + 0.015) * (1 + 0.20)
        expected_price_1 = (0.25 * (1 + 0.03) + 0.015) * (1 + 0.20)
        expected_price_2 = (0.22 * (1 + 0.03) + 0.015) * (1 + 0.20)

        self.assertAlmostEqual(prices[0], expected_price_0, places=5)
        self.assertAlmostEqual(prices[1], expected_price_1, places=5)
        self.assertAlmostEqual(prices[2], expected_price_2, places=5)

    def test_48_hour_window(self):
        """Test that 48-hour forecast window is supported"""
        energyforecast = Energyforecast(self.timezone, self.token)
        energyforecast.set_price_parameters(self.vat, self.fees, self.markup)

        # Create 48 hours of data - use timezone-aware timestamps matching Berlin timezone
        data_list = []
        base_time = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
        for hour in range(48):
            start_time = base_time + datetime.timedelta(hours=hour)
            data_list.append({
                'start': start_time.isoformat(),
                'end': (start_time + datetime.timedelta(hours=1)).isoformat(),
                'price': 0.20 + (hour * 0.001),  # Vary price slightly
                'price_origin': 'test'
            })

        raw_data = {'data': data_list}
        energyforecast.store_raw_data(raw_data)

        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.energyforecast.datetime') as mock_datetime:
            # Set current time to match the first data point
            mock_now = base_time
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = energyforecast._get_prices_native()

        # Should have prices for all 48 hours
        self.assertEqual(len(prices), 48)
        # Verify we have consecutive hours from 0 to 47
        for hour in range(48):
            self.assertIn(hour, prices, f"Hour {hour} should be present")

    def test_timezone_handling_utc(self):
        """Test correct timezone handling with UTC timestamps"""
        energyforecast = Energyforecast(self.timezone, self.token)
        energyforecast.set_price_parameters(self.vat, self.fees, self.markup)

        # Use UTC timestamp with 'Z' suffix
        raw_data = {
            'data': [
                {
                    'start': '2024-06-20T08:00:00Z',  # UTC time
                    'end': '2024-06-20T09:00:00Z',
                    'price': 0.20,
                    'price_origin': 'test'
                }
            ]
        }
        energyforecast.store_raw_data(raw_data)

        # Mock datetime to return Europe/Berlin time
        with patch('batcontrol.dynamictariff.energyforecast.datetime') as mock_datetime:
            # 08:00 UTC = 10:00 Europe/Berlin in summer
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = energyforecast._get_prices_native()

        # Should have the price at rel_hour 0
        self.assertIn(0, prices)

    def test_filter_past_prices(self):
        """Test that past prices are not included in the result"""
        energyforecast = Energyforecast(self.timezone, self.token)
        energyforecast.set_price_parameters(self.vat, self.fees, self.markup)

        raw_data = {
            'data': [
                {
                    'start': '2024-06-20T08:00:00+02:00',  # Past
                    'end': '2024-06-20T09:00:00+02:00',
                    'price': 0.18,
                    'price_origin': 'test'
                },
                {
                    'start': '2024-06-20T09:00:00+02:00',  # Past
                    'end': '2024-06-20T10:00:00+02:00',
                    'price': 0.19,
                    'price_origin': 'test'
                },
                {
                    'start': '2024-06-20T10:00:00+02:00',  # Current/future
                    'end': '2024-06-20T11:00:00+02:00',
                    'price': 0.20,
                    'price_origin': 'test'
                },
                {
                    'start': '2024-06-20T11:00:00+02:00',  # Future
                    'end': '2024-06-20T12:00:00+02:00',
                    'price': 0.21,
                    'price_origin': 'test'
                }
            ]
        }
        energyforecast.store_raw_data(raw_data)

        # Mock datetime to return 10:00
        with patch('batcontrol.dynamictariff.energyforecast.datetime') as mock_datetime:
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = energyforecast._get_prices_native()

        # Should only have future/current prices (rel_hour >= 0)
        self.assertEqual(len(prices), 2)
        self.assertIn(0, prices)
        self.assertIn(1, prices)

    def test_price_calculation_formula(self):
        """Test that the price calculation formula is correct"""
        energyforecast = Energyforecast(self.timezone, self.token)
        vat = 0.19
        fees = 0.01
        markup = 0.05
        energyforecast.set_price_parameters(vat, fees, markup)

        raw_data = {
            'data': [
                {
                    'start': '2024-06-20T10:00:00+02:00',
                    'end': '2024-06-20T11:00:00+02:00',
                    'price': 0.30,
                    'price_origin': 'test'
                }
            ]
        }
        energyforecast.store_raw_data(raw_data)

        with patch('batcontrol.dynamictariff.energyforecast.datetime') as mock_datetime:
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = energyforecast._get_prices_native()

        # Formula: (price * (1 + markup) + fees) * (1 + vat)
        # (0.30 * 1.05 + 0.01) * 1.19
        expected = (0.30 * 1.05 + 0.01) * 1.19
        self.assertAlmostEqual(prices[0], expected, places=5)

    def test_empty_forecast_data(self):
        """Test handling of empty forecast data"""
        energyforecast = Energyforecast(self.timezone, self.token)
        energyforecast.set_price_parameters(self.vat, self.fees, self.markup)

        raw_data = {'data': []}
        energyforecast.store_raw_data(raw_data)

        with patch('batcontrol.dynamictariff.energyforecast.datetime') as mock_datetime:
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = energyforecast._get_prices_native()

        # Should return empty dict
        self.assertEqual(len(prices), 0)

    def test_missing_forecast_key(self):
        """Test handling when 'data' key is missing"""
        energyforecast = Energyforecast(self.timezone, self.token)
        energyforecast.set_price_parameters(self.vat, self.fees, self.markup)

        # Store dict without 'data' key to test error handling
        raw_data = {}
        energyforecast.store_raw_data(raw_data)

        with patch('batcontrol.dynamictariff.energyforecast.datetime') as mock_datetime:
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            # Should handle missing 'data' key gracefully
            prices = energyforecast._get_prices_native()

        # Should return empty dict when 'data' key is missing
        self.assertEqual(len(prices), 0)

    def test_token_required(self):
        """Test that API token is required"""
        energyforecast = Energyforecast(self.timezone, None)
        energyforecast.set_price_parameters(self.vat, self.fees, self.markup)

        # Should raise RuntimeError when trying to get data without token
        with self.assertRaises(RuntimeError) as context:
            energyforecast.get_raw_data_from_provider()

        self.assertIn('token is required', str(context.exception).lower())


if __name__ == '__main__':
    unittest.main()
