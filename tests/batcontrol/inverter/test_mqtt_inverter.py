import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call

# Add the src directory to Python path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from batcontrol.inverter.mqtt_inverter import MqttInverter
from batcontrol.inverter.inverter import Inverter


class TestMqttInverter:
    """Test the MQTT inverter implementation"""

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_inverter_initialization(self, mock_mqtt_client):
        """Test that MQTT inverter initializes with correct configuration"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'mqtt_user': 'testuser',
            'mqtt_password': 'testpass',
            'base_topic': 'inverter',
            'capacity': 10000,
            'min_soc': 10,
            'max_soc': 95,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Check configuration
        assert inverter.mqtt_broker == '192.168.1.100'
        assert inverter.mqtt_port == 1883
        assert inverter.mqtt_user == 'testuser'
        assert inverter.mqtt_password == 'testpass'
        assert inverter.base_topic == 'inverter'
        assert inverter.capacity == 10000
        assert inverter.min_soc == 10
        assert inverter.max_soc == 95
        assert inverter.max_grid_charge_rate == 5000
        assert inverter.mode == 'allow_discharge'

        # Verify MQTT client setup
        mock_client_instance.username_pw_set.assert_called_once_with('testuser', 'testpass')
        mock_client_instance.connect.assert_called_once_with('192.168.1.100', 1883, 60)
        mock_client_instance.loop_start.assert_called_once()

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_inverter_initialization_without_auth(self, mock_mqtt_client):
        """Test MQTT inverter initialization without username/password"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Verify no auth was set
        mock_client_instance.username_pw_set.assert_not_called()

        # Should use defaults for min/max soc
        assert inverter.min_soc == 5
        assert inverter.max_soc == 100

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_on_connect_subscribes_to_topics(self, mock_mqtt_client):
        """Test that on_connect subscribes to status topics"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'test/inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Simulate connection callback
        inverter._on_connect(mock_client_instance, None, None, 0)

        # Verify subscription
        mock_client_instance.subscribe.assert_called_once_with('test/inverter/status/#')

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_message_updates_soc(self, mock_mqtt_client):
        """Test that incoming SOC messages update the cached value"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Create mock message for SOC
        mock_message = Mock()
        mock_message.topic = 'inverter/status/soc'
        mock_message.payload = b'75.5'

        # Process message
        inverter._on_message(mock_client_instance, None, mock_message)

        # Verify SOC was updated
        assert inverter.get_SOC() == 75.5

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_message_updates_capacity(self, mock_mqtt_client):
        """Test that incoming capacity messages update the cached value"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Create mock message for capacity
        mock_message = Mock()
        mock_message.topic = 'inverter/status/capacity'
        mock_message.payload = b'12000'

        # Process message
        inverter._on_message(mock_client_instance, None, mock_message)

        # Verify capacity was updated
        assert inverter.get_capacity() == 12000

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_message_updates_mode(self, mock_mqtt_client):
        """Test that incoming mode messages update the cached value"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Create mock message for mode
        mock_message = Mock()
        mock_message.topic = 'inverter/status/mode'
        mock_message.payload = b'force_charge'

        # Process message
        inverter._on_message(mock_client_instance, None, mock_message)

        # Verify mode was updated
        assert inverter.mode == 'force_charge'

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_message_updates_min_soc(self, mock_mqtt_client):
        """Test that incoming min_soc messages update the cached value"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Create mock message for min_soc
        mock_message = Mock()
        mock_message.topic = 'inverter/status/min_soc'
        mock_message.payload = b'15'

        # Process message
        inverter._on_message(mock_client_instance, None, mock_message)

        # Verify min_soc was updated
        assert inverter.min_soc == 15

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_message_updates_max_soc(self, mock_mqtt_client):
        """Test that incoming max_soc messages update the cached value"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Create mock message for max_soc
        mock_message = Mock()
        mock_message.topic = 'inverter/status/max_soc'
        mock_message.payload = b'90'

        # Process message
        inverter._on_message(mock_client_instance, None, mock_message)

        # Verify max_soc was updated
        assert inverter.max_soc == 90

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_message_updates_max_charge_rate(self, mock_mqtt_client):
        """Test that incoming max_charge_rate messages update the cached value"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Create mock message for max_charge_rate
        mock_message = Mock()
        mock_message.topic = 'inverter/status/max_charge_rate'
        mock_message.payload = b'6000'

        # Process message
        inverter._on_message(mock_client_instance, None, mock_message)

        # Verify max_charge_rate was updated
        assert inverter.max_grid_charge_rate == 6000

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_set_mode_force_charge_publishes_command(self, mock_mqtt_client):
        """Test that force charge mode publishes correct MQTT commands"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Set mode to force charge
        inverter.set_mode_force_charge(3000)

        # Verify MQTT publish calls
        assert mock_client_instance.publish.call_count == 2

        # Check mode command (QoS 1, not retained)
        mode_call = call('inverter/command/mode', 'force_charge', qos=1, retain=False)
        assert mode_call in mock_client_instance.publish.call_args_list

        # Check charge rate command (QoS 1, not retained)
        rate_call = call('inverter/command/charge_rate', '3000', qos=1, retain=False)
        assert rate_call in mock_client_instance.publish.call_args_list

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_set_mode_allow_discharge_publishes_command(self, mock_mqtt_client):
        """Test that allow discharge mode publishes correct MQTT command"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Set mode to allow discharge
        inverter.set_mode_allow_discharge()

        # Verify MQTT publish call
        mock_client_instance.publish.assert_called_once_with(
            'inverter/command/mode',
            'allow_discharge',
            qos=1,
            retain=False
        )

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_set_mode_avoid_discharge_publishes_command(self, mock_mqtt_client):
        """Test that avoid discharge mode publishes correct MQTT command"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Set mode to avoid discharge
        inverter.set_mode_avoid_discharge()

        # Verify MQTT publish call
        mock_client_instance.publish.assert_called_once_with(
            'inverter/command/mode',
            'avoid_discharge',
            qos=1,
            retain=False
        )


    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_shutdown_stops_mqtt_client(self, mock_mqtt_client):
        """Test that shutdown cleanly stops MQTT client"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Shutdown
        inverter.shutdown()

        # Verify MQTT cleanup
        mock_client_instance.loop_stop.assert_called_once()
        mock_client_instance.disconnect.assert_called_once()

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_inverter_factory_creation(self, mock_mqtt_client):
        """Test that the factory can create an MQTT inverter"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'type': 'mqtt',
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'mqtt_user': 'user',
            'mqtt_password': 'pass',
            'base_topic': 'inverter',
            'capacity': 10000,
            'min_soc': 15,
            'max_soc': 90,
            'max_grid_charge_rate': 4000
        }

        inverter = Inverter.create_inverter(config)

        # Verify it's the right type
        assert isinstance(inverter, MqttInverter)
        assert inverter.mqtt_broker == '192.168.1.100'
        assert inverter.capacity == 10000

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_mqtt_message_invalid_payload_handled_gracefully(self, mock_mqtt_client):
        """Test that invalid message payloads are handled without crashing"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Create mock message with invalid payload
        mock_message = Mock()
        mock_message.topic = 'inverter/status/soc'
        mock_message.payload = b'not_a_number'

        # Should not crash
        inverter._on_message(mock_client_instance, None, mock_message)

        if inverter.soc_key and inverter.soc_key in inverter.soc_value:
            soc_value = inverter.soc_value[inverter.soc_key]
        else:
            soc_value = None
        # SOC should still be None
        assert soc_value is None

    @patch('batcontrol.inverter.mqtt_inverter.mqtt.Client')
    def test_inherited_energy_calculations_work(self, mock_mqtt_client):
        """Test that inherited energy calculation methods work"""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        config = {
            'mqtt_broker': '192.168.1.100',
            'mqtt_port': 1883,
            'base_topic': 'inverter',
            'capacity': 10000,
            'min_soc': 10,
            'max_soc': 95,
            'max_grid_charge_rate': 5000
        }

        inverter = MqttInverter(config)

        # Simulate receiving SOC
        mock_message = Mock()
        mock_message.topic = 'inverter/status/soc'
        mock_message.payload = b'65'
        inverter._on_message(mock_client_instance, None, mock_message)

        # Test inherited methods
        stored_energy = inverter.get_stored_energy()
        assert stored_energy == 6500  # 65% of 10000 Wh

        stored_usable_energy = inverter.get_stored_usable_energy()
        assert stored_usable_energy == 5500  # (65% - 10%) of 10000 Wh

        free_capacity = inverter.get_free_capacity()
        assert free_capacity == 3000  # (95% - 65%) of 10000 Wh
