"""
Refactored ForecastSolar Factory with shared infrastructure.

This module provides a factory for solar forecast providers that use unified
fetching infrastructure including shared cache, HTTP client, and rate limiting.

Features:
- Singleton cache manager shared across all providers
- Unified HTTP client with provider-specific timeouts
- Thread-safe rate limit management
- Graceful migration path from original providers
"""
import logging
from typing import Optional

from .forecastsolar_interface import ForecastSolarInterface
from .evcc_solar import EvccSolar

# Import original providers for fallback
from .fcsolar import FCSolar
from .solarprognose import SolarPrognose

# Import shared infrastructure
from ..fetching.cache_manager import CacheManager
from ..fetching.http_client import HttpClientManager
from ..fetching.rate_limit_manager import RateLimitManager

logger = logging.getLogger(__name__)

class ForecastSolar:
    """
    Refactored ForecastSolar factory with shared infrastructure.

    Provides unified infrastructure for all solar forecast providers including:
    - Singleton cache manager
    - Shared HTTP client with provider-specific configuration
    - Thread-safe rate limit management
    - Backward compatibility with original providers
    """

    # Shared infrastructure instances (singleton pattern)
    _cache_manager: Optional[CacheManager] = None
    _http_client: Optional[HttpClientManager] = None
    _rate_limit_manager: Optional[RateLimitManager] = None

    @classmethod
    def _get_shared_infrastructure(cls):
        """
        Get or create shared infrastructure instances.

        Returns:
            tuple: (cache_manager, http_client, rate_limit_manager)
        """
        if cls._cache_manager is None:
            cls._cache_manager = CacheManager()
            logger.debug("Created shared cache manager for solar providers")

        if cls._rate_limit_manager is None:
            cls._rate_limit_manager = RateLimitManager()
            logger.debug("Created shared rate limit manager for solar providers")

        if cls._http_client is None:
            cls._http_client = HttpClientManager(rate_limit_manager=cls._rate_limit_manager)
            logger.debug("Created shared HTTP client for solar providers")

        return cls._cache_manager, cls._http_client, cls._rate_limit_manager
    @staticmethod
    def create_solar_provider(
        config: dict,
        timezone,
        api_delay: int = 0,
        requested_provider: str = 'fcsolarapi'
    ) -> ForecastSolarInterface:
        """
        Create and configure a solar forecast provider.

        Args:
            config: Configuration dictionary containing provider settings
            timezone: Timezone information
            api_delay: Random delay for API calls
            requested_provider: Provider type ('fcsolarapi', 'solarprognose', 'evcc-solar')

        Returns:
            ForecastSolarInterface: Configured solar forecast provider instance

        Raises:
            RuntimeError: If the provider type is unknown
        """
        # Get shared infrastructure for refactored providers
        (cache_manager, http_client,
         rate_limit_manager) = ForecastSolar._get_shared_infrastructure()
        logger.debug("Creating %s provider with shared infrastructure", requested_provider)

        provider = None

        if requested_provider.lower() == 'fcsolarapi':
            provider = FCSolar(
                config,
                timezone,
                api_delay,
                cache_manager=cache_manager,
                http_client=http_client
            )

        elif requested_provider.lower() == 'solarprognose':
            provider = SolarPrognose(
                config,
                timezone,
                api_delay,
                cache_manager=cache_manager,
                http_client=http_client
            )

        elif requested_provider.lower() == 'evcc-solar':
            provider = EvccSolar(
                config if isinstance(config, list) else [config],
                timezone,
                api_delay,
                cache_manager=cache_manager,
                http_client=http_client
            )

        else:
            raise RuntimeError(f'[ForecastSolar] Unknown provider {requested_provider}')

        if provider is None:
            raise RuntimeError(
                f'[ForecastSolar] Failed to create provider for {requested_provider}')

        logger.info("Created %s solar provider with shared infrastructure", requested_provider)
        return provider
    @classmethod
    def get_cache_manager(cls) -> CacheManager:
        """Get the shared cache manager instance."""
        cache_manager, _, _ = cls._get_shared_infrastructure()
        return cache_manager

    @classmethod
    def get_http_client(cls) -> HttpClientManager:
        """Get the shared HTTP client instance."""
        _, http_client, _ = cls._get_shared_infrastructure()
        return http_client

    @classmethod
    def get_rate_limit_manager(cls) -> RateLimitManager:
        """Get the shared rate limit manager instance."""
        _, _, rate_limit_manager = cls._get_shared_infrastructure()
        return rate_limit_manager

    @classmethod
    def get_cache_stats(cls) -> dict:
        """
        Get cache statistics for monitoring.

        Returns:
            dict: Cache statistics including hit rate, size, etc.
        """
        if cls._cache_manager is None:
            return {"status": "not_initialized"}

        return cls._cache_manager.get_stats()

    @classmethod
    def clear_cache(cls):
        """Clear all cached data across all providers."""
        if cls._cache_manager is not None:
            cls._cache_manager.clear()
            logger.info("Cleared all cached data for solar providers")
