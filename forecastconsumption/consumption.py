""" Factory for creating consumption forecasters. """
import logging
from .forecastconsumption_interface import ForecastConsumptionInterface
from .forecast_csv import ForecastConsumptionCsv

logger = logging.getLogger('__main__').getChild('ConsumptionFactory')
logger.info('[Consumption] loading module ')

DEFAULT_CSV_FILE = 'default_load_profile.csv'

class Consumption:
    """ Factory for consumption forecast providers """

    @staticmethod
    def create_consumption(tz, config: dict) -> ForecastConsumptionInterface:
        """ Select and configure a consumption forecast provider based on
            the given configuration segment consumption_forecast in the config file."""
        consumption = None

        # csv is the default.
        if config.get('type', 'csv').lower() == 'csv':
            csv_config = {}
            if 'csv' in config:
                csv_config = config['csv']
            else:
                # Backwards compatibility
                csv_config['annual_consumption'] = config.get('annual_consumption', 0)
                csv_config['load_profile'] = config.get('load_profile', None)

            if csv_config.get('load_profile', None) is None:
                logger.error(
                    "[Consumption] No load profile specified, using default: %s",
                    DEFAULT_CSV_FILE
                )
                csv_config['load_profile'] = DEFAULT_CSV_FILE

            consumption = ForecastConsumptionCsv(
                                'config/' + csv_config['load_profile'],
                                tz,
                                csv_config.get('annual_consumption', 0)
                            )

        return consumption
