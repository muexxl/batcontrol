"""Tests for Tibber dynamic tariff implementation"""

import datetime
import pytest
import pytz
from batcontrol.dynamictariff.tibber import Tibber


class TestTibber:
    """Test cases for Tibber class"""

    @pytest.fixture
    def timezone(self):
        """Fixture for timezone"""
        return pytz.timezone('Europe/Berlin')

    @pytest.fixture
    def tibber_instance(self, timezone):
        """Fixture for Tibber instance"""
        return Tibber(timezone, token="test_token", min_time_between_API_calls=0)

    def test_tibber_initialization(self, timezone):
        """Test Tibber initialization"""
        tibber = Tibber(timezone, token="test_token")
        assert tibber.access_token == "test_token"
        assert tibber.url == "https://api.tibber.com/v1-beta/gql"
        assert tibber.timezone == timezone

    def test_get_prices_from_raw_data_with_current_price(self, tibber_instance, timezone):
        """Test that current price is used for hour 0"""
        # Create a mock raw data structure
        now = datetime.datetime.now(timezone)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        next_hour_start = current_hour_start + datetime.timedelta(hours=1)
        
        tibber_instance.raw_data = {
            'data': {
                'viewer': {
                    'homes': [{
                        'currentSubscription': {
                            'priceInfo': {
                                'current': {
                                    'total': 0.25,
                                    'startsAt': current_hour_start.isoformat()
                                },
                                'today': [
                                    {
                                        'total': 0.20,
                                        'startsAt': current_hour_start.isoformat()
                                    },
                                    {
                                        'total': 0.26,
                                        'startsAt': next_hour_start.isoformat()
                                    }
                                ],
                                'tomorrow': []
                            }
                        }
                    }]
                }
            }
        }
        
        prices = tibber_instance.get_prices_from_raw_data()
        
        # The current price should be used (0.25), not the today price (0.20)
        assert 0 in prices
        assert prices[0] == 0.25  # Current price should be used
        assert 1 in prices
        assert prices[1] == 0.26  # Next hour from today

    def test_get_prices_from_raw_data_includes_all_future_hours(self, tibber_instance, timezone):
        """Test that all future hours from today and tomorrow are included"""
        now = datetime.datetime.now(timezone)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        tibber_instance.raw_data = {
            'data': {
                'viewer': {
                    'homes': [{
                        'currentSubscription': {
                            'priceInfo': {
                                'current': {
                                    'total': 0.25,
                                    'startsAt': current_hour_start.isoformat()
                                },
                                'today': [
                                    {
                                        'total': 0.20,
                                        'startsAt': (current_hour_start + datetime.timedelta(hours=i)).isoformat()
                                    }
                                    for i in range(0, 5)
                                ],
                                'tomorrow': [
                                    {
                                        'total': 0.30,
                                        'startsAt': (current_hour_start + datetime.timedelta(hours=24 + i)).isoformat()
                                    }
                                    for i in range(0, 3)
                                ]
                            }
                        }
                    }]
                }
            }
        }
        
        prices = tibber_instance.get_prices_from_raw_data()
        
        # Should have prices for current hour (0) plus future hours
        assert len(prices) >= 5  # At least current + 4 from today
        assert 0 in prices
        # Current hour should use current price
        assert prices[0] == 0.25

    def test_get_prices_from_raw_data_filters_past_hours(self, tibber_instance, timezone):
        """Test that past hours are not included in the result"""
        now = datetime.datetime.now(timezone)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        past_hour_start = current_hour_start - datetime.timedelta(hours=2)
        
        tibber_instance.raw_data = {
            'data': {
                'viewer': {
                    'homes': [{
                        'currentSubscription': {
                            'priceInfo': {
                                'current': {
                                    'total': 0.25,
                                    'startsAt': current_hour_start.isoformat()
                                },
                                'today': [
                                    {
                                        'total': 0.15,
                                        'startsAt': past_hour_start.isoformat()
                                    },
                                    {
                                        'total': 0.20,
                                        'startsAt': current_hour_start.isoformat()
                                    }
                                ],
                                'tomorrow': []
                            }
                        }
                    }]
                }
            }
        }
        
        prices = tibber_instance.get_prices_from_raw_data()
        
        # Should only include hour 0 (current) and future hours
        assert 0 in prices
        # Negative hours should not be present
        assert -1 not in prices
        assert -2 not in prices

    def test_get_prices_from_raw_data_current_overrides_today(self, tibber_instance, timezone):
        """Test that current price overrides the same hour in today array"""
        now = datetime.datetime.now(timezone)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        # Case where current price is different from the same hour in today
        tibber_instance.raw_data = {
            'data': {
                'viewer': {
                    'homes': [{
                        'currentSubscription': {
                            'priceInfo': {
                                'current': {
                                    'total': 0.99,  # Different from today
                                    'startsAt': current_hour_start.isoformat()
                                },
                                'today': [
                                    {
                                        'total': 0.50,  # Old value
                                        'startsAt': current_hour_start.isoformat()
                                    }
                                ],
                                'tomorrow': []
                            }
                        }
                    }]
                }
            }
        }
        
        prices = tibber_instance.get_prices_from_raw_data()
        
        # Current price should override the same hour in today array
        assert prices[0] == 0.99  # Current price takes precedence
