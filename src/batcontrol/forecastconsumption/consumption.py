""" Factory for creating consumption forecasters. """
import logging
from .forecastconsumption_interface import ForecastConsumptionInterface
from .forecast_csv import ForecastConsumptionCsv
from .forecast_homeassistant import ForecastConsumptionHomeAssistant

logger = logging.getLogger(__name__)
logger.info('Loading module')

DEFAULT_CSV_FILE = 'default_load_profile.csv'

# pylint: disable=too-few-public-methods
class Consumption:
    """ Factory for consumption forecast providers """

    @staticmethod
    def create_consumption(tz, config: dict) -> ForecastConsumptionInterface:
        """ Select and configure a consumption forecast provider based on
            the given configuration segment consumption_forecast in the config file."""
        consumption = None

        consumption_type = config.get('type', 'csv').lower()

        # csv is the default.
        if consumption_type == 'csv':
            csv_config = {}
            # Homeassistant schema validation can't handle 3rd level nesting
            if 'csv' in config:
                csv_config = config['csv']
            else:
                csv_config['annual_consumption'] = config.get('annual_consumption', 0)
                csv_config['load_profile'] = config.get('load_profile', None)

            if csv_config.get('load_profile', None) is None:
                logger.error(
                    "No load profile specified, using default: %s",
                    DEFAULT_CSV_FILE
                )
                csv_config['load_profile'] = DEFAULT_CSV_FILE

            consumption = ForecastConsumptionCsv(
                                'config/' + csv_config['load_profile'],
                                tz,
                                csv_config.get('annual_consumption', 0)
                            )

        elif consumption_type == 'homeassistant-api':
            ha_config = {}
            # HomeAssistant schema validation can't handle 3rd level nesting
            if 'homeassistant_api' in config:
                ha_config = config['homeassistant_api']
            else:
                ha_config = config


            # Validate required parameters
            required_params = ['base_url', 'apitoken', 'entity_id']
            for param in required_params:
                if param not in ha_config:
                    raise ValueError(
                        f"HomeAssistant consumption forecast requires '{param}' "
                        f"in consumption_forecast.homeassistant_api configuration"
                    )

            # Get configuration with defaults
            base_url = ha_config['base_url']
            api_token = ha_config['apitoken']
            entity_id = ha_config['entity_id']
            history_days = ha_config.get('history_days', [-7, -14, -21])
            history_weights = ha_config.get('history_weights', [1, 1, 1])

            # Convert string lists to int/float lists (HomeAssistant config quirk)
            if isinstance(history_days, list):
                history_days = [int(x) for x in history_days]
            if isinstance(history_weights, list):
                history_weights = [int(x) for x in history_weights]

            cache_ttl_hours = ha_config.get('cache_ttl_hours', 48.0)
            multiplier = ha_config.get('multiplier', 1.0)

            logger.info(
                "Creating HomeAssistant consumption forecast: "
                "entity_id=%s, history_days=%s, weights=%s, multiplier=%0.2f",
                entity_id, history_days, history_weights, multiplier
            )

            consumption = ForecastConsumptionHomeAssistant(
                base_url=base_url,
                api_token=api_token,
                entity_id=entity_id,
                timezone=tz,
                history_days=history_days,
                history_weights=history_weights,
                cache_ttl_hours=cache_ttl_hours,
                multiplier=multiplier
            )

        else:
            raise ValueError(
                f"Unknown consumption forecast type: '{consumption_type}'. "
                f"Supported types: 'csv', 'homeassistant-api'"
            )

        return consumption
