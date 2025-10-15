"""
Refactored Parent Class for implementing different tariffs.

This version inherits from BaseFetcher to eliminate code duplication
and use the unified fetching infrastructure.
"""

from abc import abstractmethod
from typing import Dict

from ..fetching.base_fetcher import BaseFetcher
from ..fetching.constants import PROVIDER_TYPE_EXTERNAL, EXTERNAL_REFRESH_INTERVAL
from .dynamictariff_interface import TariffInterface


class DynamicTariffBaseclass(BaseFetcher, TariffInterface):
    """
    Refactored Parent Class for implementing different tariffs.
    
    Inherits from both BaseFetcher (for unified fetching) and TariffInterface
    (for tariff-specific methods).
    
    This eliminates the duplicated caching, delay, and error handling logic
    that was present in the original baseclass.
    """
    
    def __init__(
        self, 
        timezone,
        min_time_between_API_calls: int = EXTERNAL_REFRESH_INTERVAL,  # Use constant (30 min)
        delay_evaluation_by_seconds: int = 0,
        **kwargs
    ):
        """
        Initialize Dynamic Tariff provider.
        
        Args:
            timezone: Timezone for the provider
            min_time_between_API_calls: Refresh interval in seconds (default from constants)
            delay_evaluation_by_seconds: Maximum random delay (passed to BaseFetcher)
            **kwargs: Additional arguments passed to BaseFetcher
        """
        # Initialize BaseFetcher with tariff-specific defaults
        super().__init__(
            timezone=timezone,
            provider_type=PROVIDER_TYPE_EXTERNAL,  # Tariff APIs are external
            refresh_interval=min_time_between_API_calls,  # Use as refresh interval
            max_delay=delay_evaluation_by_seconds,
            **kwargs
        )
        
        # Store legacy parameter for backward compatibility
        self.min_time_between_updates = min_time_between_API_calls
        
        # Store original parameters for compatibility
        self.min_time_between_updates = min_time_between_API_calls
        self.delay_evaluation_by_seconds = delay_evaluation_by_seconds
        
        # Legacy compatibility: raw_data attribute
        self._raw_data = {}
    
    @property
    def raw_data(self) -> dict:
        """Legacy compatibility property for raw_data access."""
        return self._raw_data
    
    @raw_data.setter
    def raw_data(self, value: dict):
        """Legacy compatibility setter for raw_data."""
        self._raw_data = value
    
    def get_prices(self) -> Dict[int, float]:
        """
        Get prices from provider using the unified fetching infrastructure.
        
        This method replaces the original get_prices() implementation
        with a call to the BaseFetcher.get_data() method.
        
        Returns:
            Dict mapping hour offsets to prices
        """
        # Use the unified fetching mechanism
        return self.get_data()
    
    def process_raw_data(self, raw_data: dict) -> Dict[int, float]:
        """
        Process raw data into prices format.
        
        This method calls the provider-specific get_prices_from_raw_data()
        and updates the legacy raw_data attribute for compatibility.
        
        Args:
            raw_data: Raw data from provider API
            
        Returns:
            Dict mapping hour offsets to prices
        """
        # Update legacy raw_data attribute for backward compatibility
        self._raw_data = raw_data
        
        # Call provider-specific processing
        return self.get_prices_from_raw_data()
    
    @abstractmethod
    def get_raw_data_from_provider(self) -> dict:
        """
        Fetch raw data from the tariff provider's API.
        
        This method must be implemented by subclasses to fetch
        data from their specific API endpoints.
        
        Returns:
            Raw data from the provider API
            
        Raises:
            ConnectionError: If the API request fails
        """
        raise NotImplementedError(
            "[Dynamic Tariff Base Class] Function 'get_raw_data_from_provider' not implemented"
        )
    
    @abstractmethod
    def get_prices_from_raw_data(self) -> Dict[int, float]:
        """
        Process raw data into standardized price format.
        
        This method must be implemented by subclasses to convert
        their API's raw data format into the standard price dictionary.
        
        Returns:
            Dict mapping hour offsets (0, 1, 2, ...) to prices
            
        Raises:
            ValueError: If raw data cannot be processed
        """
        raise NotImplementedError(
            "[Dynamic Tariff Base Class] Function 'get_prices_from_raw_data' not implemented"
        )
    
    def get_recommended_refresh_interval(self) -> int:
        """
        Get recommended refresh interval for tariff data.
        
        External tariff APIs typically update hourly or daily,
        so 15-minute cache duration is appropriate.
        
        Returns:
            Recommended refresh interval in seconds (900s = 15 min)
        """
        return 900  # 15 minutes for external tariff APIs