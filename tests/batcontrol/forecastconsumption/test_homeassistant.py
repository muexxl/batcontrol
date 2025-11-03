"""Tests for HomeAssistant consumption forecasting"""

import datetime
import json
from unittest.mock import patch, AsyncMock
import pytz
import pytest
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


@pytest.fixture
def mock_unit_check():
    """Mock the _check_sensor_unit method to avoid WebSocket connections in tests"""
    with patch.object(ForecastConsumptionHomeAssistant, '_check_sensor_unit', return_value=1.0):
        yield


class TestForecastConsumptionHomeAssistant:
    """Test cases for ForecastConsumptionHomeAssistant"""

    def test_initialization_default_params(self, timezone, mock_unit_check):
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

    def test_initialization_custom_params(self, base_config, mock_unit_check):
        """Test initialization with custom parameters"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        assert forecaster.history_days == [-7, -14]
        assert forecaster.history_weights == [2, 1]
        assert forecaster.cache_ttl_hours == 24.0

    def test_initialization_mismatched_lengths(self, timezone, mock_unit_check):
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

    def test_initialization_invalid_weights(self, timezone, mock_unit_check):
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

    def test_get_cache_key(self, base_config, mock_unit_check):
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

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_fetch_hourly_statistics_success(self, mock_connect, base_config, mock_unit_check):
        """Test successful fetch and processing of hourly statistics"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock WebSocket connection and messages
        mock_websocket = AsyncMock()

        # Simulate WebSocket message exchange
        mock_websocket.recv = AsyncMock(side_effect=[
            # 1. auth_required
            json.dumps({"type": "auth_required"}),
            # 2. auth_ok
            json.dumps({"type": "auth_ok"}),
            # 3. statistics response
            json.dumps({
                "id": 1,#
                "type": "result",
                "success": True,
                "result": {
                    'sensor.energy_consumption': [
                        {
                            'start': '2023-10-30T10:00:00+00:00',
                            'end': '2023-10-30T11:00:00+00:00',
                            'change': 100.5
                        },
                        {
                            'start': '2023-10-30T11:00:00+00:00',
                            'end': '2023-10-30T12:00:00+00:00',
                            'change': 110.2
                        }
                    ]
                }
            })
        ])

        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        # Make connect return an awaitable that resolves to the websocket
        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Should return float (average consumption)
        assert isinstance(result, float)
        assert result > 0  # Should have positive consumption value
        assert mock_connect.called

        # Verify WebSocket was called with correct URL
        call_args = mock_connect.call_args
        assert 'ws://localhost:8123/api/websocket' in str(call_args)

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_fetch_hourly_statistics_api_error(self, mock_connect, base_config, mock_unit_check):
        """Test handling of API errors"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock WebSocket connection failure
        async def raise_error(*args, **kwargs):
            raise Exception("Connection refused")

        mock_connect.side_effect = raise_error

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        with pytest.raises(RuntimeError, match="HomeAssistant WebSocket request failed"):
            forecaster._fetch_hourly_statistics(start, end)

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_fetch_hourly_statistics_no_data(self, mock_connect, base_config, mock_unit_check):
        """Test handling when no statistics data is available"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock WebSocket with no data
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": {}  # Empty result
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        # Make connect return an awaitable that resolves to the websocket
        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Should return -1 when no data available
        assert result == -1.0

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_fetch_hourly_statistics_negative_consumption(self, mock_connect, base_config, mock_unit_check):
        """Test handling of negative consumption (counter resets)"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock WebSocket with negative consumption
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": {
                    'sensor.energy_consumption': [
                        {
                            'start': '2023-10-30T10:00:00+00:00',
                            'end': '2023-10-30T11:00:00+00:00',
                            'change': -50.0
                        },
                        {
                            'start': '2023-10-30T11:00:00+00:00',
                            'end': '2023-10-30T12:00:00+00:00',
                            'change': 100.0
                        }
                    ]
                }
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        # Make connect return an awaitable that resolves to the websocket
        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Should skip negative values and return average of positive values only
        assert isinstance(result, float)
        assert result > 0  # Should only include the 100.0 value

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_fetch_hourly_statistics_unix_timestamps(self, mock_connect, base_config, mock_unit_check):
        """Test handling of Unix timestamps (seconds and milliseconds)"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock WebSocket with Unix timestamp in seconds
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": {
                    'sensor.energy_consumption': [
                        {
                            'start': 1698667200,  # Unix timestamp in seconds
                            'end': 1698670800,
                            'change': 100.5
                        },
                        {
                            'start': 1698670800000,  # Unix timestamp in milliseconds
                            'end': 1698674400000,
                            'change': 110.2
                        }
                    ]
                }
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        # Make connect return an awaitable that resolves to the websocket
        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Should handle both timestamp formats
        assert isinstance(result, float)
        assert result > 0  # Should have positive consumption average

    def test_update_cache_with_statistics(self, base_config, mock_unit_check):
        """Test cache update with weighted statistics"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Create sample data - now expects a list of floats (one per hour)
        # These represent average consumption values for consecutive hours
        history_periods = [100.0, 120.0, 150.0]  # 3 hours of data

        # Use a fixed timestamp for testing (Monday 10:00)
        test_timestamp = datetime.datetime(2023, 10, 30, 10, 0, tzinfo=pytz.UTC)

        # Update cache
        updated_count = forecaster._update_cache_with_statistics(test_timestamp, history_periods)

        assert updated_count == 3  # Three hour slots updated

        # Check cache contents
        with forecaster._cache_lock:
            # Monday 10:00 (first hour)
            assert '0_10' in forecaster.consumption_cache
            assert abs(forecaster.consumption_cache['0_10'] - 100.0) < 0.1

            # Monday 11:00 (second hour)
            assert '0_11' in forecaster.consumption_cache
            assert abs(forecaster.consumption_cache['0_11'] - 120.0) < 0.1

            # Monday 12:00 (third hour)
            assert '0_12' in forecaster.consumption_cache
            assert abs(forecaster.consumption_cache['0_12'] - 150.0) < 0.1

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_refresh_data(self, mock_connect, base_config, mock_unit_check):
        """Test data refresh functionality"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Mock WebSocket to return sample data
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            # Return data for each fetch call (multiple fetches will occur)
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": {
                    'sensor.energy_consumption': [
                        {
                            'start': '2023-10-30T10:00:00+00:00',
                            'change': 100.0
                        }
                    ]
                }
            })
        ] * 100)  # Repeat for multiple fetches
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        # Make connect return an awaitable that resolves to the websocket
        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        forecaster.refresh_data()

        # Check that cache was updated
        with forecaster._cache_lock:
            cache_size = len(forecaster.consumption_cache)
            assert cache_size > 0, "Cache should have been updated"

    @patch.object(ForecastConsumptionHomeAssistant, 'refresh_data')
    def test_get_forecast_with_cache(self, mock_refresh, base_config, timezone, mock_unit_check):
        """Test forecast generation with cached data"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Get current time to populate cache with appropriate keys
        now = datetime.datetime.now(tz=timezone)

        # Populate cache with test data for the next few hours from now
        with forecaster._cache_lock:
            for h in range(5):
                future_time = now + datetime.timedelta(hours=h)
                key = forecaster._get_cache_key(future_time.weekday(), future_time.hour)
                forecaster.consumption_cache[key] = 50.0 + (h * 10.0)

        # Get forecast for 3 hours
        forecast = forecaster.get_forecast(3)

        # Should not trigger refresh since cache exists
        assert not mock_refresh.called

        assert len(forecast) == 3
        for h in range(3):
            assert h in forecast
            assert forecast[h] >= 0

    @patch.object(ForecastConsumptionHomeAssistant, 'refresh_data')
    def test_get_forecast_cache_miss(self, mock_refresh, base_config, timezone, mock_unit_check):
        """Test forecast generation triggers refresh on cache miss"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Set up mock to populate cache when called
        def populate_cache():
            now = datetime.datetime.now(tz=timezone)
            with forecaster._cache_lock:
                key = forecaster._get_cache_key(now.weekday(), now.hour)
                forecaster.consumption_cache[key] = 100.0

        mock_refresh.side_effect = populate_cache

        # Get forecast with empty cache
        forecast = forecaster.get_forecast(1)

        # Should trigger refresh
        assert mock_refresh.called
        assert len(forecast) == 1

    def test_get_forecast_fallback_on_missing_key(self, base_config, timezone, mock_unit_check):
        """Test forecast stops when specific hour not in cache"""
        forecaster = ForecastConsumptionHomeAssistant(**base_config)

        # Get current time
        now = datetime.datetime.now(tz=timezone)

        # Cache with limited data - only first 2 hours from now
        with forecaster._cache_lock:
            for h in range(2):
                future_time = now + datetime.timedelta(hours=h)
                key = forecaster._get_cache_key(future_time.weekday(), future_time.hour)
                forecaster.consumption_cache[key] = 100.0 + (h * 50.0)

        # Request forecast for 5 hours - should only return 2 hours
        forecast = forecaster.get_forecast(5)

        # Should only get 2 hours since we only cached 2 hours
        assert len(forecast) == 2
        # All values should be reasonable (not 0)
        for value in forecast.values():
            assert value > 0

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_check_sensor_unit_wh(self, mock_connect, timezone):
        """Test unit check for sensor with Wh unit"""
        # Mock WebSocket connection
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "entity_id": "sensor.energy_consumption",
                        "state": "1234.5",
                        "attributes": {
                            "unit_of_measurement": "Wh",
                            "friendly_name": "Energy Consumption"
                        }
                    }
                ]
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        forecaster = ForecastConsumptionHomeAssistant(
            base_url='http://localhost:8123',
            api_token='test_token',
            entity_id='sensor.energy_consumption',
            timezone=timezone
        )

        # Should have conversion factor of 1.0 for Wh
        assert forecaster.unit_conversion_factor == 1.0

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_check_sensor_unit_kwh(self, mock_connect, timezone):
        """Test unit check for sensor with kWh unit"""
        # Mock WebSocket connection
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "entity_id": "sensor.energy_consumption",
                        "state": "1.234",
                        "attributes": {
                            "unit_of_measurement": "kWh",
                            "friendly_name": "Energy Consumption"
                        }
                    }
                ]
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        forecaster = ForecastConsumptionHomeAssistant(
            base_url='http://localhost:8123',
            api_token='test_token',
            entity_id='sensor.energy_consumption',
            timezone=timezone
        )

        # Should have conversion factor of 1000.0 for kWh
        assert forecaster.unit_conversion_factor == 1000.0

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_check_sensor_unit_invalid(self, mock_connect, timezone):
        """Test unit check for sensor with invalid unit"""
        # Mock WebSocket connection
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "entity_id": "sensor.energy_consumption",
                        "state": "1234.5",
                        "attributes": {
                            "unit_of_measurement": "MWh",
                            "friendly_name": "Energy Consumption"
                        }
                    }
                ]
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        # Should raise ValueError for unsupported unit
        with pytest.raises(ValueError, match="Unsupported unit_of_measurement 'MWh'"):
            ForecastConsumptionHomeAssistant(
                base_url='http://localhost:8123',
                api_token='test_token',
                entity_id='sensor.energy_consumption',
                timezone=timezone
            )

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_check_sensor_unit_entity_not_found(self, mock_connect, timezone):
        """Test unit check when entity is not found"""
        # Mock WebSocket connection
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "entity_id": "sensor.other_sensor",
                        "state": "100",
                        "attributes": {
                            "unit_of_measurement": "Wh"
                        }
                    }
                ]
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        # Should raise RuntimeError when entity not found
        with pytest.raises(RuntimeError, match="Entity 'sensor.energy_consumption' not found"):
            ForecastConsumptionHomeAssistant(
                base_url='http://localhost:8123',
                api_token='test_token',
                entity_id='sensor.energy_consumption',
                timezone=timezone
            )

    @patch('src.batcontrol.forecastconsumption.forecast_homeassistant.connect')
    def test_fetch_with_kwh_conversion(self, mock_connect, timezone):
        """Test that kWh values are correctly converted to Wh"""
        # Mock WebSocket connection for unit check
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=[
            # Unit check
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "entity_id": "sensor.energy_consumption",
                        "state": "1.5",
                        "attributes": {
                            "unit_of_measurement": "kWh"
                        }
                    }
                ]
            }),
            # Statistics fetch
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({
                "id": 1,
                "type": "result",
                "success": True,
                "result": {
                    'sensor.energy_consumption': [
                        {
                            'start': '2023-10-30T10:00:00+00:00',
                            'end': '2023-10-30T11:00:00+00:00',
                            'change': 1.5  # 1.5 kWh should become 1500 Wh
                        },
                        {
                            'start': '2023-10-30T11:00:00+00:00',
                            'end': '2023-10-30T12:00:00+00:00',
                            'change': 2.0  # 2.0 kWh should become 2000 Wh
                        }
                    ]
                }
            })
        ])
        mock_websocket.send = AsyncMock()
        mock_websocket.close = AsyncMock()

        async def mock_connect_coro(*args, **kwargs):
            return mock_websocket

        mock_connect.side_effect = mock_connect_coro

        forecaster = ForecastConsumptionHomeAssistant(
            base_url='http://localhost:8123',
            api_token='test_token',
            entity_id='sensor.energy_consumption',
            timezone=timezone
        )

        # Verify conversion factor is set
        assert forecaster.unit_conversion_factor == 1000.0

        start = datetime.datetime(2025, 10, 27, 0, 0, tzinfo=pytz.UTC)
        end = datetime.datetime(2025, 10, 28, 0, 0, tzinfo=pytz.UTC)

        result = forecaster._fetch_hourly_statistics(start, end)

        # Average of 1500 and 2000 Wh = 1750 Wh
        assert result == 1750.0
