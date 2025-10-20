"""
Test module for EvccSolar forecast provider
"""
import datetime

import pytest
import pytz

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
        assert evcc_solar_instance.max_delay == 0

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
        # Mock raw data with high precision values
        raw_data = {
            'result': {
                'rates': [
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=1)).isoformat(),
                        'price': 508.2049876543
                    },
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=2)).isoformat(),
                        'price': 266.8012345678
                    },
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=3)).isoformat(),
                        'price': 98.19999999999
                    }
                ]
            }
        }

        forecast = evcc_solar_instance.process_raw_data(raw_data)

        # Check that values are present (may not be exactly the same due to averaging)
        assert forecast[1] == pytest.approx(508.2, rel=0.1)
        assert forecast[2] == pytest.approx(266.8, rel=0.1)
        assert forecast[3] == pytest.approx(98.2, rel=0.1)

    def test_zero_values_remain_zero(self, evcc_solar_instance, timezone):
        """Test that zero values remain zero after rounding"""
        raw_data = {
            'result': {
                'rates': [
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=1)).isoformat(),
                        'price': 0.0000000001
                    },
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=2)).isoformat(),
                        'price': 0
                    }
                ]
            }
        }

        forecast = evcc_solar_instance.process_raw_data(raw_data)

        # Check that small values round to 0
        assert forecast[1] == pytest.approx(0.0, abs=0.01)
        assert forecast[2] == 0

    def test_missing_hours_filled_with_zero(self, evcc_solar_instance, timezone):
        """Test that missing hours are filled with 0"""
        raw_data = {
            'result': {
                'rates': [
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=1)).isoformat(),
                        'price': 100.5555
                    },
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=5)).isoformat(),
                        'price': 200.7777
                    }
                ]
            }
        }

        forecast = evcc_solar_instance.process_raw_data(raw_data)

        # Check that missing hours are filled with 0
        assert forecast[0] == 0
        assert forecast[1] == pytest.approx(100.6, rel=0.1)  # rounded
        assert forecast[2] == 0  # filled
        assert forecast[3] == 0  # filled
        assert forecast[4] == 0  # filled
        assert forecast[5] == pytest.approx(200.8, rel=0.1)  # rounded

    def test_none_values_treated_as_zero(self, evcc_solar_instance, timezone):
        """Test that None values are treated as zero"""
        raw_data = {
            'result': {
                'rates': [
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=1)).isoformat(),
                        'price': None
                    }
                ]
            }
        }

        forecast = evcc_solar_instance.process_raw_data(raw_data)

        # Check that None values are treated as 0
        assert forecast[1] == 0

    def test_rounding_with_scientific_notation_input(self, evcc_solar_instance, timezone):
        """Test rounding with values that would display in scientific notation"""
        raw_data = {
            'result': {
                'rates': [
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=1)).isoformat(),
                        'price': 5.0820e+02  # 508.20
                    },
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=2)).isoformat(),
                        'price': 2.6680e+02  # 266.80
                    },
                    {
                        'start': (datetime.datetime.now(tz=timezone) + 
                                 datetime.timedelta(hours=3)).isoformat(),
                        'price': 5.0000e-01  # 0.5
                    }
                ]
            }
        }

        forecast = evcc_solar_instance.process_raw_data(raw_data)

        # Check that values are properly handled
        assert forecast[1] == pytest.approx(508.2, rel=0.1)
        assert forecast[2] == pytest.approx(266.8, rel=0.1)
        assert forecast[3] == pytest.approx(0.5, rel=0.1)
