"""Tests for HomeAssistant consumption forecasting"""

import datetime
import pytest
import pytz
from unittest.mock import Mock, patch, MagicMock
from src.batcontrol.forecastconsumption.forecast_homeassistant import (
    ForecastConsumptionHomeAssistant
)


@pytest.fixture
def timezone():
    """Return Berlin timezone for testing"""
    return pytz.timezone('Europe/Berlin')


@pytest.fixture
def base_config(timezone):
    """Return basic configuration for HomeAssistant forecaster"""
    return {
        'base_url': 'http://localhost:8123',
        'api_token': 'test_token_12345',
        'entity_id': 'sensor.energy_consumption',
        'timezone': timezone,
        'history_days': [-7, -14],
        'history_weights': [2, 1],
        'cache_ttl_hours': 24.0
    }


class TestForecastConsumptionHomeAssistant:
    """Test cases for ForecastConsumptionHomeAssistant"""

    def test_initialization_default_params(self, timezone):
        """Test initialization with default parameters"""
        forecaster = ForecastConsumptionHomeAssistant(
            base_url='http://localhost:8123',
            api_token='test_token',
            entity_id='sensor.test',
            timezone=timezone
        )

        assert forecaster.base_url == 'http://localhost:8123'
        assert forecaster.api_token == 'test_token'
        assert forecaster.entity_id == 'sensor.test'
        assert forecaster.history_days == [-7, -14, -21]
        assert forecaster.history_weights == [1, 1, 1]
        assert forecaster.cache_ttl_hours == 48.0

    def test_initialization_custom_params(self, base_config):
        """Test initialization with custom parameters"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        assert forecaster.history_days == [-7, -14]
        assert forecaster.history_weights == [2, 1]
        assert forecaster.cache_ttl_hours == 24.0

    def test_initialization_mismatched_lengths(self, timezone):
        """Test that mismatched history_days and weights raises error"""
        with pytest.raises(ValueError, match="Length of history_days"):
            ForecastConsumptionHomeAssistant(
                base_url='http://localhost:8123',
                api_token='test_token',
                entity_id='sensor.test',
                timezone=timezone,
                history_days=[-7, -14, -21],
                history_weights=[1, 1]  # Wrong length
            )

    def test_initialization_invalid_weights(self, timezone):
        """Test that invalid weight values raise error"""
        with pytest.raises(ValueError, match="History weights must be between 1 and 10"):
            ForecastConsumptionHomeAssistant(
                base_url='http://localhost:8123',
                api_token='test_token',
                entity_id='sensor.test',
                timezone=timezone,
                history_days=[-7],
                history_weights=[15]  # Invalid weight
            )

    def test_get_cache_key(self, base_config):
        """Test cache key generation"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Monday (0) at 14:00
        key = forecaster._get_cache_key(0, 14)
        assert key == '0_14'

        # Tuesday (1) at 9:00
        key = forecaster._get_cache_key(1, 9)
        assert key == '1_9'

        # Sunday (6) at 23:00
        key = forecaster._get_cache_key(6, 23)
        assert key == '6_23'

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.requests.get')
    def test_fetch_hourly_statistics_success(self, mock_get, base_config):
        """Test successful hourly statistics fetch"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock successful API response from statistics endpoint
        # Statistics API returns dict with entity_id as key
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'sensor.energy_consumption': [
                {
                    'start': 1698667200000,  # Monday 2023-10-30 10:00:00 UTC (milliseconds)
                    'end': 1698670800000,
                    'sum': 100.5,  # Consumption in Wh
                    'state': 100.5
                },
                {
                    'start': 1698670800000,  # Monday 2023-10-30 11:00:00 UTC
                    'end': 1698674400000,
                    'sum': 110.2,
                    'state': 110.2
                }
            ]
        }
        mock_get.return_value = mock_response

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Should return dict with (weekday, hour) keys
        assert isinstance(result, dict)
        assert len(result) >= 1  # At least one hour of data
        assert mock_get.called

        # Check API call parameters
        call_args = mock_get.call_args
        assert 'Authorization' in call_args[1]['headers']
        assert 'Bearer test_token_12345' in call_args[1]['headers']['Authorization']
        assert 'statistic_ids' in call_args[1]['params']
        assert call_args[1]['params']['period'] == 'hour'

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.requests.get')
    def test_fetch_hourly_statistics_api_error(self, mock_get, base_config):
        """Test handling of API errors"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock failed API response with requests.exceptions.RequestException
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Connection refused")

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        with pytest.raises(RuntimeError, match="HomeAssistant API request failed"):
            forecaster._fetch_hourly_statistics(start, end)

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.requests.get')
    def test_fetch_hourly_statistics_no_data(self, mock_get, base_config):
        """Test handling when no statistics data is available"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock API response with no data for entity
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Empty response
        mock_get.return_value = mock_response

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Should return empty dict when no data available
        assert result == {}

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.requests.get')
    def test_fetch_hourly_statistics_negative_consumption(self, mock_get, base_config):
        """Test handling of negative consumption (counter resets)"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock API response with negative consumption
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'sensor.energy_consumption': [
                {
                    'start': 1698667200000,
                    'end': 1698670800000,
                    'sum': -50.0,  # Negative consumption (counter reset)
                    'state': -50.0
                },
                {
                    'start': 1698670800000,
                    'end': 1698674400000,
                    'sum': 100.0,  # Valid consumption
                    'state': 100.0
                }
            ]
        }
        mock_get.return_value = mock_response

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Should skip negative values
        # Only one valid hour should be in result
        assert len(result) == 1
        # Verify the valid value is present
        for value in result.values():
            assert value > 0

    def test_update_cache_with_statistics(self, base_config):
        """Test cache update with weighted statistics"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Create sample data from two periods (now with single float values)
        period1 = {
            (0, 10): 100.0,  # Monday 10:00
            (0, 11): 120.0   # Monday 11:00
        }

        period2 = {
            (0, 10): 200.0,  # Monday 10:00
            (0, 11): 220.0   # Monday 11:00
        }

        history_periods = [period1, period2]

        # Update cache
        updated_count = forecaster._update_cache_with_statistics(history_periods)

        assert updated_count == 2  # Two hour slots updated

        # Check cache contents
        with forecaster._cache_lock:
            # Weights are [2, 1] from base_config
            # Monday 10:00: (100 * 2 + 200 * 1) / 3 = 400 / 3 ≈ 133.33
            assert '0_10' in forecaster.consumption_cache
            assert abs(forecaster.consumption_cache['0_10'] - 133.33) < 0.1

            # Monday 11:00: (120 * 2 + 220 * 1) / 3 = 460 / 3 ≈ 153.33
            assert '0_11' in forecaster.consumption_cache
            assert abs(forecaster.consumption_cache['0_11'] - 153.33) < 0.1

    @patch.object(ForecastConsumptionHomeAssistant, '_fetch_hourly_statistics')
    def test_refresh_data(self, mock_fetch, base_config):
        """Test data refresh functionality"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock fetch to return sample hourly statistics
        mock_fetch.return_value = {
            (0, 10): 100.0,  # Monday 10:00
            (0, 11): 110.0   # Monday 11:00
        }

        forecaster.refresh_data()

        # Check that fetch was called for each history period
        assert mock_fetch.call_count == len(base_config['history_days'])

        # Check that cache was updated
        with forecaster._cache_lock:
            cache_size = len(forecaster.consumption_cache)
            assert cache_size > 0, "Cache should have been updated"

    @patch.object(ForecastConsumptionHomeAssistant, 'refresh_data')
    def test_get_forecast_with_cache(self, mock_refresh, base_config):
        """Test forecast generation with cached data"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Populate cache with test data using new numeric keys
        with forecaster._cache_lock:
            forecaster.consumption_cache['0_0'] = 50.0   # Monday 00:00
            forecaster.consumption_cache['0_1'] = 45.0   # Monday 01:00
            forecaster.consumption_cache['0_10'] = 100.0  # Monday 10:00
            forecaster.consumption_cache['0_11'] = 110.0  # Monday 11:00
            forecaster.consumption_cache['1_10'] = 95.0   # Tuesday 10:00

        # Get forecast for 3 hours
        forecast = forecaster.get_forecast(3)

        # Should not trigger refresh since cache exists
        assert not mock_refresh.called

        assert len(forecast) == 3
        for h in range(3):
            assert h in forecast
            assert forecast[h] >= 0

    @patch.object(ForecastConsumptionHomeAssistant, 'refresh_data')
    def test_get_forecast_cache_miss(self, mock_refresh, base_config):
        """Test forecast generation triggers refresh on cache miss"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Set up mock to populate cache when called
        def populate_cache():
            with forecaster._cache_lock:
                forecaster.consumption_cache['0_10'] = 100.0

        mock_refresh.side_effect = populate_cache

        # Get forecast with empty cache
        forecast = forecaster.get_forecast(1)

        # Should trigger refresh
        assert mock_refresh.called
        assert len(forecast) == 1

    def test_get_forecast_fallback_on_missing_key(self, base_config):
        """Test forecast uses average when specific hour not in cache"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Cache with limited data using new numeric keys
        with forecaster._cache_lock:
            forecaster.consumption_cache['0_10'] = 100.0  # Monday 10:00
            forecaster.consumption_cache['1_10'] = 200.0  # Tuesday 10:00

        # Request forecast - will use average for missing hours
        forecast = forecaster.get_forecast(5)

        assert len(forecast) == 5
        # All values should be reasonable (not 0, using average)
        for value in forecast.values():
            assert value > 0
