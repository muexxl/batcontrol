"""
Test cases for the Tibber dynamic tariff class.
"""
import unittest
import datetime
from unittest.mock import patch
import pytz
from batcontrol.dynamictariff.tibber import Tibber


class TestTibber(unittest.TestCase):
    """Test cases for Tibber API integration"""
    def setUp(self):
        """Set up test fixtures"""
        self.timezone = pytz.timezone('Europe/Berlin')
        self.token = 'test_token_12345'

    def test_get_prices_from_raw_data(self):
        """Test that get_prices_from_raw_data correctly fetches from cache"""
        tibber = Tibber(self.timezone, self.token)

        # Mock raw data with Tibber API format
        raw_data = {
            'data': {
                'viewer': {
                    'homes': [
                        {
                            'currentSubscription': {
                                'priceInfo': {
                                    'current': {
                                        'total': 0.25,
                                        'startsAt': '2024-06-20T10:00:00+02:00'
                                    },
                                    'today': [
                                        {
                                            'total': 0.25,
                                            'startsAt': '2024-06-20T10:00:00+02:00'
                                        },
                                        {
                                            'total': 0.30,
                                            'startsAt': '2024-06-20T11:00:00+02:00'
                                        },
                                        {
                                            'total': 0.28,
                                            'startsAt': '2024-06-20T12:00:00+02:00'
                                        }
                                    ],
                                    'tomorrow': [
                                        {
                                            'total': 0.27,
                                            'startsAt': '2024-06-21T10:00:00+02:00'
                                        }
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }
        tibber.store_raw_data(raw_data)

        # Mock datetime to return a specific time
        with patch('batcontrol.dynamictariff.tibber.datetime') as mock_datetime:
            # Set current time to 10:00 so all prices are in the future
            # Use localize for proper timezone handling with pytz
            mock_now = self.timezone.localize(
                datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = tibber.get_prices_from_raw_data()

        # Verify prices are extracted correctly
        self.assertEqual(prices[0], 0.25)  # Current hour (10:00)
        self.assertEqual(prices[1], 0.30)  # Next hour (11:00)
        self.assertEqual(prices[2], 0.28)  # Hour after (12:00)
        self.assertIn(24, prices)  # Tomorrow at 10:00
        self.assertEqual(prices[24], 0.27)

    def test_get_prices_from_raw_data_empty_cache(self):
        """Test that get_prices_from_raw_data handles empty cache gracefully"""
        tibber = Tibber(self.timezone, self.token)

        # Don't store any data - cache is empty
        # This should raise an error when trying to access raw data
        with self.assertRaises(Exception):
            tibber.get_prices_from_raw_data()

    def test_multiple_homes_uses_first_home(self):
        """Test that Tibber uses the first home (index 0) from multiple homes"""
        tibber = Tibber(self.timezone, self.token)

        # Mock raw data with multiple homes
        raw_data = {
            'data': {
                'viewer': {
                    'homes': [
                        {
                            'currentSubscription': {
                                'priceInfo': {
                                    'current': {
                                        'total': 0.25,
                                        'startsAt': '2024-06-20T10:00:00+02:00'
                                    },
                                    'today': [
                                        {
                                            'total': 0.25,
                                            'startsAt': '2024-06-20T10:00:00+02:00'
                                        }
                                    ],
                                    'tomorrow': []
                                }
                            }
                        },
                        {
                            'currentSubscription': {
                                'priceInfo': {
                                    'current': {
                                        'total': 0.99,
                                        'startsAt': '2024-06-20T10:00:00+02:00'
                                    },
                                    'today': [
                                        {
                                            'total': 0.99,
                                            'startsAt': '2024-06-20T10:00:00+02:00'
                                        }
                                    ],
                                    'tomorrow': []
                                }
                            }
                        }
                    ]
                }
            }
        }
        tibber.store_raw_data(raw_data)

        with patch('batcontrol.dynamictariff.tibber.datetime') as mock_datetime:
            mock_now = self.timezone.localize(
                datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = tibber.get_prices_from_raw_data()

        # Should use the first home's price (0.25) not the second home's (0.99)
        self.assertEqual(prices[0], 0.25)

    def test_filter_past_prices(self):
        """Test that past prices are filtered out correctly"""
        tibber = Tibber(self.timezone, self.token)

        # Mock raw data with prices before and after current time
        raw_data = {
            'data': {
                'viewer': {
                    'homes': [
                        {
                            'currentSubscription': {
                                'priceInfo': {
                                    'current': {
                                        'total': 0.25,
                                        'startsAt': '2024-06-20T10:00:00+02:00'
                                    },
                                    'today': [
                                        # Past
                                        {'total': 0.20,
                                         'startsAt': '2024-06-20T08:00:00+02:00'},
                                        # Past
                                        {'total': 0.22,
                                         'startsAt': '2024-06-20T09:00:00+02:00'},
                                        # Now
                                        {'total': 0.25,
                                         'startsAt': '2024-06-20T10:00:00+02:00'},
                                        # Future
                                        {'total': 0.30,
                                         'startsAt': '2024-06-20T11:00:00+02:00'}
                                    ],
                                    'tomorrow': []
                                }
                            }
                        }
                    ]
                }
            }
        }
        tibber.store_raw_data(raw_data)

        with patch('batcontrol.dynamictariff.tibber.datetime') as mock_datetime:
            mock_now = self.timezone.localize(
                datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat

            prices = tibber.get_prices_from_raw_data()

        # Should only have current and future prices, not past ones
        self.assertIn(0, prices)  # Current hour
        self.assertIn(1, prices)  # Next hour
        # Past prices should not be included (negative rel_hour values)
        # Check that we don't have prices for negative hours
        for rel_hour in prices:
            self.assertGreaterEqual(rel_hour, 0)


if __name__ == '__main__':
    unittest.main()
