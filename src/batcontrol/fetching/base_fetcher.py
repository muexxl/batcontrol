"""
Base fetcher class providing common patterns for all data providers.

This class consolidates the duplicated caching, delay, error handling,
and rate limiting logic found across all providers.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Optional
import logging

from .constants import (
    EXTERNAL_CACHE_TTL,
    LOCAL_CACHE_TTL,
    EXTERNAL_REFRESH_INTERVAL,
    LOCAL_REFRESH_INTERVAL,
    DEFAULT_MAX_DELAY,
    PROVIDER_TYPE_EXTERNAL,
    PROVIDER_TYPE_LOCAL
)
from .cache_manager import CacheManager
from .http_client import HttpClientManager
from .rate_limit_manager import RateLimitManager

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    """
    Base class for all data fetchers (solar, tariff, consumption).
    
    Provides unified:
    - Caching with configurable TTL
    - Random delay implementation
    - Rate limit handling
    - Error handling patterns
    - Provider-specific configuration
    
    Subclasses need to implement:
    - get_raw_data_from_provider(): Fetch data from API
    - process_raw_data(): Convert raw data to expected format
    - get_provider_id(): Unique provider identifier
    """
    
    def __init__(
        self,
        timezone,
        provider_type: str = PROVIDER_TYPE_EXTERNAL,
        cache_ttl: Optional[int] = None,
        refresh_interval: Optional[int] = None,
        max_delay: int = DEFAULT_MAX_DELAY,
        shared_cache_manager: Optional[CacheManager] = None,
        shared_http_client: Optional[HttpClientManager] = None
    ):
        """
        Initialize base fetcher.
        
        Args:
            timezone: Timezone for the provider
            provider_type: 'external' or 'local' - affects timeouts and defaults
            cache_ttl: Cache TTL in seconds (24h default for both types)
            refresh_interval: Refresh interval in seconds (30min external, 15min local)
            max_delay: Maximum random delay in seconds
            shared_cache_manager: Shared cache manager instance
            shared_http_client: Shared HTTP client instance
        """
        self.timezone = timezone
        self.provider_type = provider_type
        self.max_delay = max_delay
        self.last_update = 0
        
        # Set default cache TTL based on provider type (24h for both)
        if cache_ttl is None:
            if provider_type == PROVIDER_TYPE_LOCAL:
                self.cache_ttl = LOCAL_CACHE_TTL  # 24h
            else:
                self.cache_ttl = EXTERNAL_CACHE_TTL  # 24h
        else:
            self.cache_ttl = cache_ttl
        
        # Set default refresh interval based on provider type
        if refresh_interval is None:
            if provider_type == PROVIDER_TYPE_LOCAL:
                self.refresh_interval = LOCAL_REFRESH_INTERVAL  # 15min
            else:
                self.refresh_interval = EXTERNAL_REFRESH_INTERVAL  # 30min
        else:
            self.refresh_interval = refresh_interval
        
        # Legacy compatibility: cache_duration = cache_ttl
        self.cache_duration = self.cache_ttl
        
        # Initialize managers (shared or individual)
        self.cache_manager = shared_cache_manager or CacheManager()
        self.http_client = shared_http_client or HttpClientManager()
        
        # Cache key for this provider instance
        self._cache_key = f"{self.get_provider_id()}_{id(self)}"
        
        logger.info(f"Initialized {self.get_provider_id()} provider "
                   f"(type: {provider_type}, cache_ttl: {self.cache_ttl}s, "
                   f"refresh_interval: {self.refresh_interval}s)")
    
    @abstractmethod
    def get_provider_id(self) -> str:
        """Return unique identifier for this provider."""
        pass
    
    @abstractmethod
    def get_raw_data_from_provider(self) -> Any:
        """Fetch raw data from the provider's API."""
        pass
    
    @abstractmethod
    def process_raw_data(self, raw_data: Any) -> Any:
        """Process raw data into the expected format."""
        pass
    
    def get_data(self) -> Any:
        """
        Main method to get data with caching, rate limiting, and error handling.
        
        This method implements the common pattern found in all providers:
        1. Check if cache is valid
        2. If not, apply random delay
        3. Fetch new data from provider
        4. Process and cache the data
        5. Return processed data
        
        Returns:
            Processed data in expected format
        """
        provider_id = self.get_provider_id()
        current_time = time.time()
        
        # Check if we need to update (cache expired)
        time_since_update = current_time - self.last_update
        if time_since_update <= self.cache_ttl:
            # Try to get from cache
            cached_data = self.cache_manager.get(self._cache_key)
            if cached_data is not None:
                logger.debug(f"[{provider_id}] Using cached data "
                           f"(age: {time_since_update:.1f}s)")
                return cached_data
        
        # Cache miss or expired - fetch new data
        logger.debug(f"[{provider_id}] Cache miss, fetching new data "
                    f"(last update: {time_since_update:.1f}s ago)")
        
        try:
            # Fetch raw data with rate limiting and delays
            raw_data = self._fetch_with_error_handling()
            
            # Process raw data
            processed_data = self.process_raw_data(raw_data)
            
            # Update cache and timestamp
            self.cache_manager.set(self._cache_key, processed_data, self.cache_ttl)
            self.last_update = current_time
            
            logger.info(f"[{provider_id}] Successfully fetched and cached new data")
            return processed_data
            
        except Exception as e:
            # Try to use cached data as fallback
            cached_data = self.cache_manager.get(self._cache_key)
            if cached_data is not None:
                logger.warning(f"[{provider_id}] Using cached data due to error: {e}")
                return cached_data
            else:
                logger.error(f"[{provider_id}] No cached data available, re-raising error")
                raise
    
    def _fetch_with_error_handling(self) -> Any:
        """
        Fetch raw data with unified error handling patterns.
        
        Returns:
            Raw data from provider
            
        Raises:
            ConnectionError: If fetch fails and no fallback available
        """
        provider_id = self.get_provider_id()
        
        try:
            # Apply random delay (handled by HTTP client)
            raw_data = self.get_raw_data_from_provider()
            return raw_data
            
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"[{provider_id}] Network error during fetch: {e}")
            raise
        except Exception as e:
            logger.error(f"[{provider_id}] Unexpected error during fetch: {e}", exc_info=True)
            # Convert to ConnectionError for consistent handling
            raise ConnectionError(f"[{provider_id}] Fetch failed: {e}") from e
    
    def get_recommended_refresh_interval(self) -> int:
        """
        Get recommended refresh interval for this provider.
        
        This is separate from cache TTL - determines how often background
        fetching should update the data.
        
        Returns:
            Refresh interval in seconds
        """
        return self.refresh_interval
    
    def invalidate_cache(self):
        """Manually invalidate cache for this provider."""
        self.cache_manager.invalidate(self._cache_key)
        logger.info(f"[{self.get_provider_id()}] Cache invalidated")
    
    def get_cache_info(self) -> dict:
        """Get information about cache status for this provider."""
        cached_data = self.cache_manager.get(self._cache_key)
        time_since_update = time.time() - self.last_update
        
        return {
            'provider_id': self.get_provider_id(),
            'has_cached_data': cached_data is not None,
            'cache_ttl': self.cache_ttl,
            'refresh_interval': self.refresh_interval,
            'time_since_update': time_since_update,
            'cache_valid': time_since_update <= self.cache_ttl,
            'last_update': self.last_update
        }
    
    def force_refresh(self) -> Any:
        """Force refresh of data, bypassing cache."""
        logger.info(f"[{self.get_provider_id()}] Forcing refresh")
        self.invalidate_cache()
        self.last_update = 0  # Force update on next get_data() call
        return self.get_data()