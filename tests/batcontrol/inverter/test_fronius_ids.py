"""Tests for Fronius inverter configurable IDs."""
import unittest
from unittest.mock import Mock, patch
import json
from packaging import version

from batcontrol.inverter.fronius import FroniusWR


class TestFroniusConfigurableIDs(unittest.TestCase):
    """Test configurable inverter and controller IDs."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_config = {
            'address': '192.168.1.100',
            'user': 'customer',
            'password': 'testpass',
            'max_grid_charge_rate': 5000,
            'max_pv_charge_rate': 0
        }

    def _setup_mocks(self, mock_get_firmware, mock_get_battery, mock_get_powerunit):
        """Helper method to set up common mocks."""
        mock_get_firmware.return_value = version.parse("1.36.0")
        mock_get_battery.return_value = {
            'HYB_EM_MODE': 0,
            'HYB_EM_POWER': 0,
            'BAT_M0_SOC_MIN': 5,
            'BAT_M0_SOC_MAX': 100,
            'HYB_BACKUP_RESERVED': 10
        }
        mock_get_powerunit.return_value = {
            'backuppower': {'DEVICE_MODE_BACKUPMODE_TYPE_U16': 0}
        }

    @patch('batcontrol.inverter.fronius.FroniusWR.get_firmware_version')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_battery_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_powerunit_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.backup_time_of_use')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_solar_api_active')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_allow_grid_charging')
    def test_default_inverter_id(self, mock_set_allow, mock_set_solar, mock_backup_tou,
                                 mock_get_powerunit, mock_get_battery, mock_get_firmware):
        """Test that default inverter_id is '1' when not specified."""
        self._setup_mocks(mock_get_firmware,
                          mock_get_battery, mock_get_powerunit)

        # Create inverter without specifying fronius_inverter_id
        inverter = FroniusWR(self.base_config)

        # Assert default value
        self.assertEqual(inverter.inverter_id, '1')

    @patch('batcontrol.inverter.fronius.FroniusWR.get_firmware_version')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_battery_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_powerunit_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.backup_time_of_use')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_solar_api_active')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_allow_grid_charging')
    def test_default_controller_id(self, mock_set_allow, mock_set_solar, mock_backup_tou,
                                   mock_get_powerunit, mock_get_battery, mock_get_firmware):
        """Test that default controller_id is '0' when not specified."""
        self._setup_mocks(mock_get_firmware,
                          mock_get_battery, mock_get_powerunit)

        # Create inverter without specifying fronius_controller_id
        inverter = FroniusWR(self.base_config)

        # Assert default value
        self.assertEqual(inverter.controller_id, '0')

    @patch('batcontrol.inverter.fronius.FroniusWR.get_firmware_version')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_battery_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_powerunit_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.backup_time_of_use')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_solar_api_active')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_allow_grid_charging')
    def test_custom_inverter_id(self, mock_set_allow, mock_set_solar, mock_backup_tou,
                                mock_get_powerunit, mock_get_battery, mock_get_firmware):
        """Test that custom inverter_id can be set."""
        self._setup_mocks(mock_get_firmware,
                          mock_get_battery, mock_get_powerunit)

        # Create inverter with custom fronius_inverter_id
        config = self.base_config.copy()
        config['fronius_inverter_id'] = '2'
        inverter = FroniusWR(config)

        # Assert custom value
        self.assertEqual(inverter.inverter_id, '2')

    @patch('batcontrol.inverter.fronius.FroniusWR.get_firmware_version')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_battery_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_powerunit_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.backup_time_of_use')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_solar_api_active')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_allow_grid_charging')
    def test_custom_controller_id(self, mock_set_allow, mock_set_solar, mock_backup_tou,
                                  mock_get_powerunit, mock_get_battery, mock_get_firmware):
        """Test that custom controller_id can be set."""
        self._setup_mocks(mock_get_firmware,
                          mock_get_battery, mock_get_powerunit)

        # Create inverter with custom fronius_controller_id
        config = self.base_config.copy()
        config['fronius_controller_id'] = '3'
        inverter = FroniusWR(config)

        # Assert custom value
        self.assertEqual(inverter.controller_id, '3')

        # Create inverter with custom fronius_controller_id
        config = self.base_config.copy()
        config['fronius_controller_id'] = '3'
        inverter = FroniusWR(config)

        # Assert custom value
        self.assertEqual(inverter.controller_id, '3')

    @patch('batcontrol.inverter.fronius.FroniusWR.get_firmware_version')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_battery_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_powerunit_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.backup_time_of_use')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_solar_api_active')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_allow_grid_charging')
    @patch('batcontrol.inverter.fronius.FroniusWR.send_request')
    def test_get_soc_uses_inverter_id(self, mock_send_request, mock_set_allow, mock_set_solar,
                                      mock_backup_tou, mock_get_powerunit, mock_get_battery,
                                      mock_get_firmware):
        """Test that get_SOC uses the configured inverter_id."""
        self._setup_mocks(mock_get_firmware,
                          mock_get_battery, mock_get_powerunit)

        # Create mock response with SOC data for inverter ID '2'
        mock_response = Mock()
        mock_response.text = json.dumps({
            'Body': {
                'Data': {
                    'Inverters': {
                        '2': {'SOC': 75.5}
                    }
                }
            }
        })
        mock_send_request.return_value = mock_response

        # Create inverter with custom inverter_id
        config = self.base_config.copy()
        config['fronius_inverter_id'] = '2'
        inverter = FroniusWR(config)

        # Get SOC
        soc = inverter.get_SOC()

        # Assert SOC is read from correct inverter ID
        self.assertEqual(soc, 75.5)

    @patch('batcontrol.inverter.fronius.FroniusWR.get_firmware_version')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_battery_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_powerunit_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.backup_time_of_use')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_solar_api_active')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_allow_grid_charging')
    @patch('batcontrol.inverter.fronius.FroniusWR.send_request')
    def test_get_capacity_uses_controller_id(self, mock_send_request, mock_set_allow,
                                             mock_set_solar, mock_backup_tou,
                                             mock_get_powerunit, mock_get_battery,
                                             mock_get_firmware):
        """Test that get_capacity uses the configured controller_id."""
        self._setup_mocks(mock_get_firmware,
                          mock_get_battery, mock_get_powerunit)

        # Create mock response with capacity data for controller ID '1'
        mock_response = Mock()
        mock_response.text = json.dumps({
            'Body': {
                'Data': {
                    '1': {
                        'Controller': {'DesignedCapacity': 12500}
                    }
                }
            }
        })
        mock_send_request.return_value = mock_response

        # Create inverter with custom controller_id
        config = self.base_config.copy()
        config['fronius_controller_id'] = '1'
        inverter = FroniusWR(config)

        # Get capacity
        capacity = inverter.get_capacity()

        # Assert capacity is read from correct controller ID
        self.assertEqual(capacity, 12500)

    @patch('batcontrol.inverter.fronius.FroniusWR.get_firmware_version')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_battery_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.get_powerunit_config')
    @patch('batcontrol.inverter.fronius.FroniusWR.backup_time_of_use')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_solar_api_active')
    @patch('batcontrol.inverter.fronius.FroniusWR.set_allow_grid_charging')
    def test_ids_converted_to_string(self, mock_set_allow, mock_set_solar, mock_backup_tou,
                                     mock_get_powerunit, mock_get_battery, mock_get_firmware):
        """Test that IDs are converted to strings even if provided as integers."""
        self._setup_mocks(mock_get_firmware,
                          mock_get_battery, mock_get_powerunit)

        # Create inverter with integer IDs
        config = self.base_config.copy()
        config['fronius_inverter_id'] = 2
        config['fronius_controller_id'] = 1
        inverter = FroniusWR(config)

        # Assert IDs are strings
        self.assertIsInstance(inverter.inverter_id, str)
        self.assertIsInstance(inverter.controller_id, str)
        self.assertEqual(inverter.inverter_id, '2')
        self.assertEqual(inverter.controller_id, '1')


if __name__ == '__main__':
    unittest.main()
