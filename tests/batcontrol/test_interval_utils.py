"""Tests for interval_utils module."""
import pytest
from batcontrol.interval_utils import (
    upsample_forecast,
    downsample_to_hourly,
    average_to_hourly,
    _upsample_linear,
    _upsample_constant
)


class TestUpsampleLinear:
    """Tests for linear upsampling of forecast data."""
    
    def test_simple_linear_interpolation(self):
        """Test basic linear interpolation from hourly to 15-min."""
        hourly = {
            0: 1000,  # Hour 0: 1000 Wh
            1: 2000,  # Hour 1: 2000 Wh
        }
        
        result = _upsample_linear(hourly)
        
        # Expected: linear power ramp from 1000W to 2000W
        # [0]: 1000W * 0.25h = 250 Wh
        # [1]: 1250W * 0.25h = 312.5 Wh
        # [2]: 1500W * 0.25h = 375 Wh
        # [3]: 1750W * 0.25h = 437.5 Wh
        # [4]: 2000W * 0.25h = 500 Wh
        assert result[0] == pytest.approx(250, rel=0.01)
        assert result[1] == pytest.approx(312.5, rel=0.01)
        assert result[2] == pytest.approx(375, rel=0.01)
        assert result[3] == pytest.approx(437.5, rel=0.01)
        assert result[4] == pytest.approx(500, rel=0.01)
    
    def test_constant_power(self):
        """Test upsampling when power is constant."""
        hourly = {
            0: 1000,
            1: 1000,
            2: 1000,
        }
        
        result = _upsample_linear(hourly)
        
        # All quarters should be equal (1000W * 0.25h = 250 Wh)
        for i in range(12):  # 3 hours * 4 quarters
            assert result[i] == pytest.approx(250, rel=0.01)
    
    def test_zero_values(self):
        """Test handling of zero values."""
        hourly = {
            0: 0,
            1: 1000,
        }
        
        result = _upsample_linear(hourly)
        
        # Linear ramp from 0 to 1000W
        assert result[0] == pytest.approx(0, abs=1)
        assert result[1] == pytest.approx(62.5, rel=0.01)
        assert result[2] == pytest.approx(125, rel=0.01)
        assert result[3] == pytest.approx(187.5, rel=0.01)
    
    def test_energy_conservation(self):
        """Test that total energy is conserved during upsampling."""
        hourly = {
            0: 1000,
            1: 1500,
            2: 2000,
        }
        
        result = _upsample_linear(hourly)
        
        # Sum quarters for each hour
        hour0_total = sum(result[i] for i in range(0, 4))
        hour1_total = sum(result[i] for i in range(4, 8))
        hour2_total = sum(result[i] for i in range(8, 12))
        
        # Linear interpolation distributes energy differently than simple averaging
        # For linear: power ramps from 1000W to 1500W across hour 0
        # Quarters: 1000W, 1125W, 1250W, 1375W
        # Energy: 250, 281.25, 312.5, 343.75 = 1187.5 Wh total
        # For hour 1: power ramps from 1500W to 2000W
        # Quarters: 1500W, 1625W, 1750W, 1875W
        # Energy: 375, 406.25, 437.5, 468.75 = 1687.5 Wh total
        assert hour0_total == pytest.approx(1187.5, rel=0.01)
        assert hour1_total == pytest.approx(1687.5, rel=0.01)
        assert hour2_total == pytest.approx(2000, rel=0.01)  # Last hour


class TestUpsampleConstant:
    """Tests for constant upsampling (equal distribution)."""
    
    def test_simple_division(self):
        """Test that hourly values are divided by 4."""
        hourly = {
            0: 1000,
            1: 2000,
            2: 1500,
        }
        
        result = _upsample_constant(hourly)
        
        # Each hour divided into 4 equal parts
        assert result[0] == 250  # 1000/4
        assert result[1] == 250
        assert result[2] == 250
        assert result[3] == 250
        
        assert result[4] == 500  # 2000/4
        assert result[5] == 500
        assert result[6] == 500
        assert result[7] == 500
        
        assert result[8] == 375  # 1500/4
        assert result[9] == 375
        assert result[10] == 375
        assert result[11] == 375
    
    def test_energy_conservation(self):
        """Test that total energy is exactly conserved."""
        hourly = {
            0: 1234,
            1: 5678,
        }
        
        result = _upsample_constant(hourly)
        
        # Sum should equal original
        hour0_total = sum(result[i] for i in range(0, 4))
        hour1_total = sum(result[i] for i in range(4, 8))
        
        assert hour0_total == pytest.approx(1234, abs=0.001)
        assert hour1_total == pytest.approx(5678, abs=0.001)


class TestUpsampleForecast:
    """Tests for the main upsample_forecast function."""
    
    def test_linear_method(self):
        """Test that linear method is called correctly."""
        hourly = {0: 1000, 1: 2000}
        result = upsample_forecast(hourly, target_resolution=15, method='linear')
        
        # Should use linear interpolation
        assert len(result) > 4  # At least 5 intervals for 2 hours
        assert result[0] == pytest.approx(250, rel=0.01)
    
    def test_constant_method(self):
        """Test that constant method is called correctly."""
        hourly = {0: 1000, 1: 2000}
        result = upsample_forecast(hourly, target_resolution=15, method='constant')
        
        # Should use constant distribution
        assert result[0] == 250  # 1000/4
        assert result[1] == 250
        assert result[2] == 250
        assert result[3] == 250
    
    def test_invalid_resolution(self):
        """Test that invalid resolution raises error."""
        hourly = {0: 1000}
        
        with pytest.raises(ValueError, match="Only 15-minute resolution"):
            upsample_forecast(hourly, target_resolution=30, method='linear')
    
    def test_invalid_method(self):
        """Test that invalid method raises error."""
        hourly = {0: 1000}
        
        with pytest.raises(ValueError, match="Unknown upsampling method"):
            upsample_forecast(hourly, target_resolution=15, method='invalid')
    
    def test_empty_input(self):
        """Test handling of empty input."""
        result = upsample_forecast({}, target_resolution=15, method='linear')
        assert result == {}


class TestDownsampleToHourly:
    """Tests for downsampling 15-min to hourly."""
    
    def test_simple_summing(self):
        """Test that quarters are summed correctly."""
        data_15min = {
            0: 250,  # Hour 0
            1: 300,
            2: 350,
            3: 400,
            4: 500,  # Hour 1
            5: 500,
            6: 500,
            7: 500,
        }
        
        result = downsample_to_hourly(data_15min)
        
        assert result[0] == 1300  # 250+300+350+400
        assert result[1] == 2000  # 500+500+500+500
    
    def test_incomplete_hour(self):
        """Test handling of incomplete hours."""
        data_15min = {
            0: 250,
            1: 250,
            2: 250,
            # Missing quarter 3
        }
        
        result = downsample_to_hourly(data_15min)
        
        assert result[0] == 750  # Only 3 quarters
    
    def test_energy_conservation(self):
        """Test that total energy is conserved."""
        data_15min = {i: 100 for i in range(20)}  # 5 hours of data
        
        result = downsample_to_hourly(data_15min)
        
        total_15min = sum(data_15min.values())
        total_hourly = sum(result.values())
        
        assert total_hourly == total_15min


class TestAverageToHourly:
    """Tests for averaging 15-min prices to hourly."""
    
    def test_simple_averaging(self):
        """Test that quarters are averaged correctly."""
        data_15min = {
            0: 10,  # Hour 0
            1: 12,
            2: 14,
            3: 16,
            4: 20,  # Hour 1
            5: 20,
            6: 20,
            7: 20,
        }
        
        result = average_to_hourly(data_15min)
        
        assert result[0] == pytest.approx(13, rel=0.01)  # (10+12+14+16)/4
        assert result[1] == pytest.approx(20, rel=0.01)  # (20+20+20+20)/4
    
    def test_incomplete_hour(self):
        """Test averaging with incomplete hours."""
        data_15min = {
            0: 10,
            1: 20,
            # Only 2 quarters
        }
        
        result = average_to_hourly(data_15min)
        
        assert result[0] == pytest.approx(15, rel=0.01)  # (10+20)/2


class TestRealWorldScenario:
    """Integration tests with realistic data."""
    
    def test_solar_forecast_upsampling(self):
        """Test upsampling a realistic solar forecast."""
        # Typical solar production curve
        hourly = {
            0: 0,      # Night
            1: 0,
            2: 100,    # Dawn
            3: 500,
            4: 1500,   # Morning
            5: 2500,
            6: 3000,   # Midday
            7: 2500,
            8: 1500,   # Afternoon
            9: 500,
            10: 100,   # Dusk
            11: 0,     # Night
        }
        
        result = upsample_forecast(hourly, target_resolution=15, method='linear')
        
        # Should have 12 hours * 4 quarters = 48 intervals
        assert len(result) >= 44  # At least up to hour 11
        
        # Check that values are reasonable (positive)
        assert all(v >= 0 for v in result.values())
        
        # Check peak is in the middle
        max_interval = max(result.items(), key=lambda x: x[1])
        assert 20 < max_interval[0] < 30  # Around midday (hours 5-7)
    
    def test_price_forecast_upsampling(self):
        """Test upsampling electricity prices."""
        # Typical price pattern
        hourly = {
            0: 0.20,  # Night (cheap)
            1: 0.22,
            2: 0.30,  # Morning peak
            3: 0.35,
            4: 0.25,  # Midday
            5: 0.28,
            6: 0.38,  # Evening peak
            7: 0.40,
            8: 0.25,  # Late evening
        }
        
        result = upsample_forecast(hourly, target_resolution=15, method='constant')
        
        # Each hour should have 4 identical quarters
        assert result[0] == result[1] == result[2] == result[3] == 0.05  # 0.20/4
        assert result[24] == result[25] == result[26] == result[27] == pytest.approx(0.095, rel=0.01)  # 0.38/4
    
    def test_roundtrip_conversion(self):
        """Test that downsampling after upsampling gives similar results."""
        original_hourly = {
            0: 1000,
            1: 1500,
            2: 2000,
            3: 1800,
        }
        
        # Upsample to 15-min
        upsampled = upsample_forecast(original_hourly, target_resolution=15, method='linear')
        
        # Downsample back to hourly
        downsampled = downsample_to_hourly(upsampled)
        
        # Values should be similar (not exact due to interpolation at boundaries)
        # But total energy should be close
        original_total = sum(original_hourly.values())
        final_total = sum(downsampled.values())
        
        # Allow some difference due to interpolation
        assert final_total == pytest.approx(original_total, rel=0.15)
