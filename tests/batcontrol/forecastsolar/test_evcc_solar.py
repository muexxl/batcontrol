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
        return [{'url': 'http://localhost:7070/api/tariff/solar'}]

    @pytest.fixture
    def evcc_solar_instance(self, pvinstallations, timezone):
        """Fixture for EvccSolar instance"""
        return EvccSolar(pvinstallations, timezone, api_delay=0)

    def test_initialization(self, evcc_solar_instance):
        """Test that EvccSolar initializes correctly"""
        assert evcc_solar_instance.url == 'http://localhost:7070/api/tariff/solar'
        assert evcc_solar_instance.api_delay == 0

    def test_initialization_without_url(self, timezone):
        """Test that initialization fails without URL"""
        with pytest.raises(ValueError, match="URL must be provided"):
            EvccSolar([{}], timezone, api_delay=0)

    def test_initialization_multiple_installations(self, timezone):
        """Test that initialization fails with multiple installations"""
        with pytest.raises(ValueError, match="exactly one installation"):
            EvccSolar([{'url': 'url1'}, {'url': 'url2'}], timezone, api_delay=0)

    def test_values_rounded_to_one_decimal(self, evcc_solar_instance, timezone):
        """Test that forecast values are rounded to 1 decimal place"""
        from unittest.mock import patch
        
        # Mock raw data with high precision values
        evcc_solar_instance.raw_data = {
            'rates': [
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'value': 508.2049876543
                },
                {
                    'start': '2024-06-20T12:00:00+02:00',
                    'value': 266.8012345678
                },
                {
                    'start': '2024-06-20T13:00:00+02:00',
                    'value': 98.19999999999
                }
            ]
        }

        # Mock datetime to return a consistent time
        with patch('batcontrol.forecastsolar.evcc_solar.datetime') as mock_datetime:
            # Set current time to 10:00 so all forecasts are in the future
            mock_now = timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            forecast = evcc_solar_instance._get_forecast_from_raw_data()

        # Check that values are rounded to 1 decimal place
        assert forecast[1] == 508.2
        assert forecast[2] == 266.8
        assert forecast[3] == 98.2

    def test_zero_values_remain_zero(self, evcc_solar_instance, timezone):
        """Test that zero values remain zero after rounding"""
        from unittest.mock import patch
        
        evcc_solar_instance.raw_data = {
            'rates': [
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'value': 0.0000000001
                },
                {
                    'start': '2024-06-20T12:00:00+02:00',
                    'value': 0
                }
            ]
        }

        # Mock datetime to return a consistent time
        with patch('batcontrol.forecastsolar.evcc_solar.datetime') as mock_datetime:
            # Set current time to 10:00 so all forecasts are in the future
            mock_now = timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            forecast = evcc_solar_instance._get_forecast_from_raw_data()

        # Check that small values round to 0
        assert forecast[1] == 0.0
        assert forecast[2] == 0

    def test_missing_hours_filled_with_zero(self, evcc_solar_instance, timezone):
        """Test that missing hours are filled with 0"""
        from unittest.mock import patch
        
        evcc_solar_instance.raw_data = {
            'rates': [
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'value': 100.5555
                },
                {
                    'start': '2024-06-20T15:00:00+02:00',
                    'value': 200.7777
                }
            ]
        }

        # Mock datetime to return a consistent time
        with patch('batcontrol.forecastsolar.evcc_solar.datetime') as mock_datetime:
            # Set current time to 10:00 so all forecasts are in the future
            mock_now = timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            forecast = evcc_solar_instance._get_forecast_from_raw_data()

        # Check that missing hours are filled with 0
        assert forecast[0] == 0
        assert forecast[1] == 100.6  # rounded
        assert forecast[2] == 0  # filled
        assert forecast[3] == 0  # filled
        assert forecast[4] == 0  # filled
        assert forecast[5] == 200.8  # rounded

    def test_none_values_treated_as_zero(self, evcc_solar_instance, timezone):
        """Test that None values are treated as zero"""
        from unittest.mock import patch
        
        evcc_solar_instance.raw_data = {
            'rates': [
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'value': None
                }
            ]
        }

        # Mock datetime to return a consistent time
        with patch('batcontrol.forecastsolar.evcc_solar.datetime') as mock_datetime:
            # Set current time to 10:00 so all forecasts are in the future
            mock_now = timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            forecast = evcc_solar_instance._get_forecast_from_raw_data()

        # Check that None values are treated as 0
        assert forecast[1] == 0

    def test_rounding_with_scientific_notation_input(self, evcc_solar_instance, timezone):
        """Test rounding with values that would display in scientific notation"""
        from unittest.mock import patch
        
        evcc_solar_instance.raw_data = {
            'rates': [
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'value': 5.0820e+02  # 508.20
                },
                {
                    'start': '2024-06-20T12:00:00+02:00',
                    'value': 2.6680e+02  # 266.80
                },
                {
                    'start': '2024-06-20T13:00:00+02:00',
                    'value': 5.0000e-01  # 0.5
                }
            ]
        }

        # Mock datetime to return a consistent time
        with patch('batcontrol.forecastsolar.evcc_solar.datetime') as mock_datetime:
            # Set current time to 10:00 so all forecasts are in the future
            mock_now = timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            forecast = evcc_solar_instance._get_forecast_from_raw_data()

        # Check that values are properly rounded
        assert forecast[1] == 508.2
        assert forecast[2] == 266.8
        assert forecast[3] == 0.5

    def test_multiple_values_per_hour_averaging(self, evcc_solar_instance, timezone):
        """Test averaging when multiple forecast values exist for the same hour (15-minute intervals)"""
        from unittest.mock import patch
        
        # Mock raw data with 15-minute intervals (4 values per hour)
        evcc_solar_instance.raw_data = {
            'rates': [
                # Hour 0: values 100, 200, 300, 400 -> average 250.0
                {
                    'start': '2024-06-20T10:00:00+02:00',
                    'value': 100
                },
                {
                    'start': '2024-06-20T10:15:00+02:00',
                    'value': 200
                },
                {
                    'start': '2024-06-20T10:30:00+02:00',
                    'value': 300
                },
                {
                    'start': '2024-06-20T10:45:00+02:00',
                    'value': 400
                },
                # Hour 1: values 500, 600, 700, 800 -> average 650.0
                {
                    'start': '2024-06-20T11:00:00+02:00',
                    'value': 500
                },
                {
                    'start': '2024-06-20T11:15:00+02:00',
                    'value': 600
                },
                {
                    'start': '2024-06-20T11:30:00+02:00',
                    'value': 700
                },
                {
                    'start': '2024-06-20T11:45:00+02:00',
                    'value': 800
                }
            ]
        }

        # Mock datetime to return a consistent time
        with patch('batcontrol.forecastsolar.evcc_solar.datetime') as mock_datetime:
            # Set current time to 10:00 so all forecasts are in the future
            mock_now = timezone.localize(datetime.datetime(2024, 6, 20, 10, 0, 0))
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
            
            forecast = evcc_solar_instance._get_forecast_from_raw_data()

        # Hour 0 should be average of 100, 200, 300, 400 = 250.0
        assert forecast[0] == 250.0
        # Hour 1 should be average of 500, 600, 700, 800 = 650.0
        assert forecast[1] == 650.0
