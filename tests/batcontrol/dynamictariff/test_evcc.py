import unittest
import datetime
import pytz
from unittest.mock import Mock, patch
from batcontrol.dynamictariff.evcc import Evcc


class TestEvcc(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.timezone = pytz.timezone('Europe/Berlin')
        self.url = 'http://test.example.com/api/prices'
        
    def test_single_price_per_hour(self):
        """Test backward compatibility with one price per hour"""
        evcc = Evcc(self.timezone, self.url)
        
        # Mock raw data with one price per hour
        evcc.raw_data = {
            'rates': [
                {
                    'start': '2024-06-20T10:00:00+02:00',
                    'end': '2024-06-20T11:00:00+02:00',
                    'value': 0.25
                },
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'end': '2024-06-20T12:00:00+02:00',
                    'value': 0.30
                },
                {
                    'start': '2024-06-20T12:00:00+02:00',
                    'end': '2024-06-20T13:00:00+02:00',
                    'value': 0.28
                }
            ]
        }
        
        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.evcc.datetime') as mock_datetime:
            # Set current time to 10:00 so all prices are in the future
            # Use localize for proper timezone handling with pytz
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            prices = evcc.get_prices_from_raw_data()
            
        # Each hour should have exactly the value provided
        self.assertEqual(prices[0], 0.25)
        self.assertEqual(prices[1], 0.30)
        self.assertEqual(prices[2], 0.28)
        
    def test_multiple_prices_per_hour_averaging(self):
        """Test averaging when multiple prices exist for the same hour"""
        evcc = Evcc(self.timezone, self.url)
        
        # Mock raw data with 15-minute intervals (4 prices per hour)
        evcc.raw_data = {
            'rates': [
                # Hour 0: prices 0.20, 0.22, 0.24, 0.26 -> average 0.23
                {
                    'start': '2024-06-20T10:00:00+02:00',
                    'end': '2024-06-20T10:15:00+02:00',
                    'value': 0.20
                },
                {
                    'start': '2024-06-20T10:15:00+02:00',
                    'end': '2024-06-20T10:30:00+02:00',
                    'value': 0.22
                },
                {
                    'start': '2024-06-20T10:30:00+02:00',
                    'end': '2024-06-20T10:45:00+02:00',
                    'value': 0.24
                },
                {
                    'start': '2024-06-20T10:45:00+02:00',
                    'end': '2024-06-20T11:00:00+02:00',
                    'value': 0.26
                },
                # Hour 1: prices 0.30, 0.32, 0.34, 0.36 -> average 0.33
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'end': '2024-06-20T11:15:00+02:00',
                    'value': 0.30
                },
                {
                    'start': '2024-06-20T11:15:00+02:00',
                    'end': '2024-06-20T11:30:00+02:00',
                    'value': 0.32
                },
                {
                    'start': '2024-06-20T11:30:00+02:00',
                    'end': '2024-06-20T11:45:00+02:00',
                    'value': 0.34
                },
                {
                    'start': '2024-06-20T11:45:00+02:00',
                    'end': '2024-06-20T12:00:00+02:00',
                    'value': 0.36
                }
            ]
        }
        
        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.evcc.datetime') as mock_datetime:
            # Set current time to 10:00 so all prices are in the future
            # Use localize for proper timezone handling with pytz
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            prices = evcc.get_prices_from_raw_data()
            
        # Hour 0 should be average of 0.20, 0.22, 0.24, 0.26 = 0.23
        self.assertAlmostEqual(prices[0], 0.23, places=5)
        # Hour 1 should be average of 0.30, 0.32, 0.34, 0.36 = 0.33
        self.assertAlmostEqual(prices[1], 0.33, places=5)
        
    def test_price_field_compatibility(self):
        """Test compatibility with 'price' field (pre-0.203.0)"""
        evcc = Evcc(self.timezone, self.url)
        
        # Mock raw data using 'price' instead of 'value'
        evcc.raw_data = {
            'rates': [
                {
                    'start': '2024-06-20T10:00:00+02:00',
                    'end': '2024-06-20T10:15:00+02:00',
                    'price': 0.20
                },
                {
                    'start': '2024-06-20T10:15:00+02:00',
                    'end': '2024-06-20T10:30:00+02:00',
                    'price': 0.22
                },
                {
                    'start': '2024-06-20T10:30:00+02:00',
                    'end': '2024-06-20T10:45:00+02:00',
                    'price': 0.24
                },
                {
                    'start': '2024-06-20T10:45:00+02:00',
                    'end': '2024-06-20T11:00:00+02:00',
                    'price': 0.26
                }
            ]
        }
        
        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.evcc.datetime') as mock_datetime:
            # Set current time to 10:00 so all prices are in the future
            # Use localize for proper timezone handling with pytz
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            prices = evcc.get_prices_from_raw_data()
            
        # Should average the four 15-minute prices: (0.20 + 0.22 + 0.24 + 0.26) / 4 = 0.23
        self.assertAlmostEqual(prices[0], 0.23, places=5)
        
    def test_result_field_compatibility(self):
        """Test compatibility with old API format (pre-0.207.0)"""
        evcc = Evcc(self.timezone, self.url)
        
        # Mock raw data with old format
        evcc.raw_data = {
            'result': {
                'rates': [
                    {
                        'start': '2024-06-20T10:00:00+02:00',
                        'end': '2024-06-20T11:00:00+02:00',
                        'price': 0.25
                    }
                ]
            }
        }
        
        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.evcc.datetime') as mock_datetime:
            # Set current time to 10:00 so all prices are in the future
            # Use localize for proper timezone handling with pytz
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            prices = evcc.get_prices_from_raw_data()
            
        self.assertEqual(prices[0], 0.25)
        
    def test_mixed_single_and_multiple_prices(self):
        """Test with some hours having one price and others having multiple"""
        evcc = Evcc(self.timezone, self.url)
        
        # Mock raw data with mixed granularity
        evcc.raw_data = {
            'rates': [
                # Hour 0: single price
                {
                    'start': '2024-06-20T10:00:00+02:00',
                    'end': '2024-06-20T11:00:00+02:00',
                    'value': 0.25
                },
                # Hour 1: four 15-minute prices (average should be 0.33)
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'end': '2024-06-20T11:15:00+02:00',
                    'value': 0.30
                },
                {
                    'start': '2024-06-20T11:15:00+02:00',
                    'end': '2024-06-20T11:30:00+02:00',
                    'value': 0.32
                },
                {
                    'start': '2024-06-20T11:30:00+02:00',
                    'end': '2024-06-20T11:45:00+02:00',
                    'value': 0.34
                },
                {
                    'start': '2024-06-20T11:45:00+02:00',
                    'end': '2024-06-20T12:00:00+02:00',
                    'value': 0.36
                },
                # Hour 2: single price
                {
                    'start': '2024-06-20T12:00:00+02:00',
                    'end': '2024-06-20T13:00:00+02:00',
                    'value': 0.28
                }
            ]
        }
        
        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.evcc.datetime') as mock_datetime:
            # Set current time to 10:00 so all prices are in the future
            # Use localize for proper timezone handling with pytz
            mock_now = self.timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            prices = evcc.get_prices_from_raw_data()
            
        # Hour 0: single price of 0.25
        self.assertEqual(prices[0], 0.25)
        # Hour 1: average of four prices
        self.assertAlmostEqual(prices[1], 0.33, places=5)
        # Hour 2: single price of 0.28
        self.assertEqual(prices[2], 0.28)


if __name__ == '__main__':
    unittest.main()
