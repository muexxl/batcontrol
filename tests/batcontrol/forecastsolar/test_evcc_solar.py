"""
Test module for EvccSolar forecast provider
"""
import pytest
import datetime
import pytz
from unittest.mock import MagicMock, patch
from batcontrol.forecastsolar.evcc_solar import EvccSolar


class TestEvccSolar:
    """Tests for EvccSolar class"""

    @pytest.fixture
    def timezone(self):
        """Fixture for timezone"""
        return pytz.timezone('Europe/Berlin')

    @pytest.fixture
    def pvinstallations(self):
        """Fixture for PV installations config"""
        return [{'name': 'default' , 'url': 'http://localhost:7070/api/tariff/solar'}]

    @pytest.fixture
    def evcc_solar_instance(self, pvinstallations, timezone):
        """Fixture for EvccSolar instance"""
        return EvccSolar(pvinstallations, timezone, min_time_between_api_calls=900, api_delay=0)

    def test_initialization(self, evcc_solar_instance):
        """Test that EvccSolar initializes correctly"""
        assert evcc_solar_instance.url == 'http://localhost:7070/api/tariff/solar'
        assert evcc_solar_instance.delay_evaluation_by_seconds == 0

    def test_initialization_without_url(self, timezone):
        """Test that initialization fails without URL"""
        with pytest.raises(ValueError, match="URL must be provided"):
            EvccSolar([{'name': 'default'}], timezone, min_time_between_api_calls=900, api_delay=0)

    def test_initialization_multiple_installations(self, timezone):
        """Test that initialization fails with multiple installations"""
        with pytest.raises(ValueError, match="exactly one installation"):
            EvccSolar([{'name': 'default', 'url': 'url1'}, {'name': 'another', 'url': 'url2'}],
                       timezone, min_time_between_api_calls=900, api_delay=0)

    def test_values_rounded_to_one_decimal(self, evcc_solar_instance, timezone):
        """Test that forecast values are rounded to 1 decimal place"""
        # Mock raw data with high precision values (15-minute intervals)
        # Align to start of current hour for predictable indexing
        now = datetime.datetime.now(tz=timezone)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        evcc_solar_instance.store_raw_data('default', {
            'rates': [
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=15)).isoformat(),
                    'value': 508.2049876543
                },
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=30)).isoformat(),
                    'value': 266.8012345678
                },
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=45)).isoformat(),
                    'value': 98.19999999999
                }
            ]
        })

        forecast = evcc_solar_instance.get_forecast_from_raw_data()

        # Check that values are rounded to 1 decimal place
        # Values are converted from W to Wh (W * 0.25)
        assert forecast[1] == pytest.approx(508.2 * 0.25, abs=0.1)  # Index 1 = 15-min interval
        assert forecast[2] == pytest.approx(266.8 * 0.25, abs=0.1)  # Index 2 = 30-min interval  
        assert forecast[3] == pytest.approx(98.2 * 0.25, abs=0.1)   # Index 3 = 45-min interval

    def test_zero_values_remain_zero(self, evcc_solar_instance, timezone):
        """Test that zero values remain zero after rounding"""
        evcc_solar_instance.store_raw_data('default', {
            'rates': [
                {
                    'start': (datetime.datetime.now(tz=timezone) +
                             datetime.timedelta(hours=1)).isoformat(),
                    'value': 0.0000000001
                },
                {
                    'start': (datetime.datetime.now(tz=timezone) +
                             datetime.timedelta(hours=2)).isoformat(),
                    'value': 0
                }
            ]
        })

        forecast = evcc_solar_instance.get_forecast_from_raw_data()

        # Check that small values round to 0
        assert forecast[1] == 0.0
        assert forecast[2] == 0

    def test_missing_hours_filled_with_zero(self, evcc_solar_instance, timezone):
        """Test that missing intervals are filled with 0"""
        now = datetime.datetime.now(tz=timezone)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        evcc_solar_instance.store_raw_data('default', {
            'rates': [
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=15)).isoformat(),
                    'value': 100.5555
                },
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=75)).isoformat(),  # 1h15m = 5 intervals
                    'value': 200.7777
                }
            ]
        })

        forecast = evcc_solar_instance.get_forecast_from_raw_data()

        # Check that missing intervals are filled with 0
        assert forecast[0] == 0
        assert forecast[1] == pytest.approx(100.6 * 0.25, abs=0.1)  # Index 1, converted to Wh
        assert forecast[2] == 0  # filled
        assert forecast[3] == 0  # filled
        assert forecast[4] == 0  # filled
        assert forecast[5] == pytest.approx(200.8 * 0.25, abs=0.1)  # Index 5, converted to Wh

    def test_none_values_treated_as_zero(self, evcc_solar_instance, timezone):
        """Test that None values are treated as zero"""
        evcc_solar_instance.store_raw_data('default', {
            'rates': [
                {
                    'start': (datetime.datetime.now(tz=timezone) +
                             datetime.timedelta(hours=1)).isoformat(),
                    'value': None
                }
            ]
        })

        forecast = evcc_solar_instance.get_forecast_from_raw_data()

        # Check that None values are treated as 0
        assert forecast[1] == 0

    def test_rounding_with_scientific_notation_input(self, evcc_solar_instance, timezone):
        """Test rounding with values that would display in scientific notation"""
        now = datetime.datetime.now(tz=timezone)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        evcc_solar_instance.store_raw_data('default', {
            'rates': [
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=15)).isoformat(),
                    'value': 5.0820e+02  # 508.20 W
                },
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=30)).isoformat(),
                    'value': 2.6680e+02  # 266.80 W
                },
                {
                    'start': (current_hour_start + datetime.timedelta(minutes=45)).isoformat(),
                    'value': 5.0000e-01  # 0.5 W
                }
            ]
        })

        forecast = evcc_solar_instance.get_forecast_from_raw_data()

        # Check that values are properly rounded and converted to Wh
        assert forecast[1] == pytest.approx(508.2 * 0.25, abs=0.1)
        assert forecast[2] == pytest.approx(266.8 * 0.25, abs=0.1)
        assert forecast[3] == pytest.approx(0.5 * 0.25, abs=0.1)
