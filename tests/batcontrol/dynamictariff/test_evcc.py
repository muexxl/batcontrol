"""Tests for the Evcc dynamic tariff class"""
import unittest
import datetime
import pytz
from batcontrol.dynamictariff.evcc import Evcc


class TestEvccPriceAveraging(unittest.TestCase):
    """Test suite for Evcc price averaging functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.timezone = pytz.timezone('Europe/Berlin')
        self.url = "http://test.example.com/api/tariff"
        self.evcc = Evcc(self.timezone, self.url)
        
        # Use current hour as the base time for testing
        # This will map to rel_hour = 0 (current hour), 1 (next hour), etc.
        now = datetime.datetime.now(self.timezone)
        self.base_time = now.replace(minute=0, second=0, microsecond=0)

    def _format_timestamp(self, hours_offset):
        """Helper to create ISO timestamp for testing"""
        ts = self.base_time + datetime.timedelta(hours=hours_offset)
        return ts.isoformat()

    def test_single_price_per_hour(self):
        """Test that single price per hour is returned as-is"""
        # Mock raw data with one price per hour
        self.evcc.raw_data = {
            'rates': [
                {'start': self._format_timestamp(0), 'value': 0.30},
                {'start': self._format_timestamp(1), 'value': 0.35},
                {'start': self._format_timestamp(2), 'value': 0.25},
            ]
        }
            
        prices = self.evcc.get_prices_from_raw_data()

        # Each hour should have its price unchanged
        self.assertEqual(len(prices), 3)
        self.assertEqual(prices[0], 0.30)  # Hour 0
        self.assertEqual(prices[1], 0.35)  # Hour 1
        self.assertEqual(prices[2], 0.25)  # Hour 2

    def test_multiple_prices_per_hour_averaging(self):
        """Test that multiple prices per hour are averaged correctly"""
        # Mock raw data with multiple prices per hour (e.g., every 15 minutes)
        self.evcc.raw_data = {
            'rates': [
                # Hour 0: Four 15-minute intervals
                {'start': self._format_timestamp(0), 'value': 0.20},
                {'start': (self.base_time + datetime.timedelta(minutes=15)).isoformat(), 'value': 0.24},
                {'start': (self.base_time + datetime.timedelta(minutes=30)).isoformat(), 'value': 0.28},
                {'start': (self.base_time + datetime.timedelta(minutes=45)).isoformat(), 'value': 0.32},
                # Hour 1: Four 15-minute intervals
                {'start': self._format_timestamp(1), 'value': 0.30},
                {'start': (self.base_time + datetime.timedelta(hours=1, minutes=15)).isoformat(), 'value': 0.34},
                {'start': (self.base_time + datetime.timedelta(hours=1, minutes=30)).isoformat(), 'value': 0.38},
                {'start': (self.base_time + datetime.timedelta(hours=1, minutes=45)).isoformat(), 'value': 0.42},
            ]
        }
            
        prices = self.evcc.get_prices_from_raw_data()

        # Should have 2 hours with averaged prices
        self.assertEqual(len(prices), 2)
        
        # Hour 0 average: (0.20 + 0.24 + 0.28 + 0.32) / 4 = 0.26
        self.assertAlmostEqual(prices[0], 0.26, places=6)
        
        # Hour 1 average: (0.30 + 0.34 + 0.38 + 0.42) / 4 = 0.36
        self.assertAlmostEqual(prices[1], 0.36, places=6)

    def test_mixed_price_intervals(self):
        """Test averaging with different numbers of entries per hour"""
        # Mock raw data with varying numbers of prices per hour
        self.evcc.raw_data = {
            'rates': [
                # Hour 0: Two entries
                {'start': self._format_timestamp(0), 'value': 0.20},
                {'start': (self.base_time + datetime.timedelta(minutes=30)).isoformat(), 'value': 0.30},
                # Hour 1: One entry
                {'start': self._format_timestamp(1), 'value': 0.35},
                # Hour 2: Four entries
                {'start': self._format_timestamp(2), 'value': 0.10},
                {'start': (self.base_time + datetime.timedelta(hours=2, minutes=15)).isoformat(), 'value': 0.14},
                {'start': (self.base_time + datetime.timedelta(hours=2, minutes=30)).isoformat(), 'value': 0.18},
                {'start': (self.base_time + datetime.timedelta(hours=2, minutes=45)).isoformat(), 'value': 0.22},
            ]
        }
            
        prices = self.evcc.get_prices_from_raw_data()

        # Should have 3 hours
        self.assertEqual(len(prices), 3)
        
        # Hour 0 average: (0.20 + 0.30) / 2 = 0.25
        self.assertAlmostEqual(prices[0], 0.25, places=6)
        
        # Hour 1: single value = 0.35
        self.assertAlmostEqual(prices[1], 0.35, places=6)
        
        # Hour 2 average: (0.10 + 0.14 + 0.18 + 0.22) / 4 = 0.16
        self.assertAlmostEqual(prices[2], 0.16, places=6)

    def test_legacy_price_field(self):
        """Test that legacy 'price' field (pre-0.203.0) works with averaging"""
        # Mock raw data using 'price' instead of 'value'
        self.evcc.raw_data = {
            'rates': [
                {'start': self._format_timestamp(0), 'price': 0.20},
                {'start': (self.base_time + datetime.timedelta(minutes=30)).isoformat(), 'price': 0.30},
            ]
        }
            
        prices = self.evcc.get_prices_from_raw_data()

        # Should average the two prices
        self.assertEqual(len(prices), 1)
        self.assertAlmostEqual(prices[0], 0.25, places=6)

    def test_old_api_format(self):
        """Test that old API format (pre-0.207.0) with 'result' field works"""
        # Mock raw data in old format with rates in result.rates
        self.evcc.raw_data = {
            'result': {
                'rates': [
                    {'start': self._format_timestamp(0), 'price': 0.20},
                    {'start': (self.base_time + datetime.timedelta(minutes=30)).isoformat(), 'price': 0.30},
                ]
            }
        }
            
        prices = self.evcc.get_prices_from_raw_data()

        # Should average the two prices
        self.assertEqual(len(prices), 1)
        self.assertAlmostEqual(prices[0], 0.25, places=6)


if __name__ == '__main__':
    unittest.main()
