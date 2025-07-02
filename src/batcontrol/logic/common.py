""" This module contains battery control logic, that is not specific to control strategies.
It includes the handling of:

  - is always allowed discharge
  - charge_rate multiplier
  """
import logging


# Minimum charge rate to controlling loops between charging and
#   self discharge.
# 500W is Fronius' internal value for forced recharge.
MIN_CHARGE_RATE = 500


logger = logging.getLogger(__name__)

# Singleton pattern to ensure only one instance of CommonLogic exists
class CommonLogic:
    """ General logic for battery control that is not specific to control strategies. """

    _instance = None  # Singleton instance
    charge_rate_multiplier: float
    always_allow_discharge_limit: float
    max_capacity: float  # Maximum capacity of the battery in Wh

    @classmethod
    def get_instance(cls, charge_rate_multiplier=1.1,
                     always_allow_discharge_limit=0.9,
                     max_capacity=10000) -> "CommonLogic":
        """ Get the singleton instance of CommonLogic. """
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance.__init(charge_rate_multiplier,
                                 always_allow_discharge_limit,
                                 max_capacity)
        return cls._instance

    def __init__(self, *args, **kwargs):
        """ This method is overridden to prevent direct instantiation. """
        if CommonLogic._instance is not None:
            raise RuntimeError(
                "Use CommonLogic.get_instance() instead of constructor")
        self.__init(*args, **kwargs)

    def __init(self, charge_rate_multiplier=1.1,
               always_allow_discharge_limit=0.9,
               max_capacity=10000):
        """ Private initialization method. """
        self.charge_rate_multiplier = charge_rate_multiplier
        self.always_allow_discharge_limit = always_allow_discharge_limit
        self.max_capacity = max_capacity

    def set_charge_rate_multiplier(self, multiplier: float):
        """ Set the charge rate multiplier. """
        logger.debug('Setting charge rate multiplier to %s', multiplier)
        self.charge_rate_multiplier = multiplier

    def set_always_allow_discharge_limit(self, limit: float):
        """ Set the always allowed discharge limit. """
        logger.debug(
            'Setting always allowed discharge limit to %s', limit)
        self.always_allow_discharge_limit = limit

    def get_always_allow_discharge_limit(self) -> float:
        """ Get the always allowed discharge limit. """
        return self.always_allow_discharge_limit

    def is_discharge_always_allowed_soc(self, soc: float) -> bool:
        """ Check if discharge is always allowed based on the state of charge (SOC). 
        Args:
            soc (float): State of charge as a percentage (0-100).
        Returns:
            bool: True if discharge is always allowed, False otherwise."""
        if soc/100 >= self.always_allow_discharge_limit:
            logger.debug('Discharge is always allowed for SOC: %s', soc)
            return True
        logger.debug('Discharge is NOT always allowed for SOC: %s', soc)
        return False

    def is_discharge_always_allowed_capacity(self, capacity: float) -> bool:
        """ Check if discharge is always allowed based on the battery capacity.
        Args:
            capacity (float): Battery capacity in Wh.
        Returns:
            bool: True if discharge is always allowed, False otherwise."""

        if capacity >= self.max_capacity * self.always_allow_discharge_limit:
            logger.debug(
                'Discharge is always allowed for capacity: %s', capacity)
            return True
        logger.debug(
            'Discharge is NOT always allowed for capacity: %s', capacity)
        return False


    def calculate_charge_rate(self, charge_rate: float) -> float:
        """ Calculate the charge rate based on the charge rate multiplier.
        Args:
            charge_rate (float): The initial charge rate in W.
        Returns:
            float: The adjusted charge rate in W."""
        logger.debug('Calculating charge rate: %s', charge_rate)
        adjusted_charge_rate = charge_rate * self.charge_rate_multiplier
        if adjusted_charge_rate < MIN_CHARGE_RATE:
            logger.debug(
                'Charge rate increased to minimum %d W from %f.1 W',
                MIN_CHARGE_RATE, adjusted_charge_rate)
            adjusted_charge_rate = MIN_CHARGE_RATE

        logger.debug('Adjusted charge rate: %s', adjusted_charge_rate)
        return adjusted_charge_rate
