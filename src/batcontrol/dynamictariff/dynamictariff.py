"""
Refactored DynamicTariff Factory with shared infrastructure.

This module provides a factory for dynamic tariff providers that use unified
fetching infrastructure including shared cache, HTTP client, and rate limiting.

Features:
- Singleton cache manager shared across all providers
- Unified HTTP client with provider-specific timeouts
- Thread-safe rate limit management
- Graceful migration path from original providers
"""
import logging
from typing import Optional

from .awattar import Awattar
from .tibber import Tibber
from .evcc import Evcc
from .dynamictariff_interface import TariffInterface

# Import shared infrastructure
from ..fetching.cache_manager import CacheManager
from ..fetching.http_client import HttpClientManager
from ..fetching.rate_limit_manager import RateLimitManager

logger = logging.getLogger(__name__)

class DynamicTariff:
    """
    Refactored DynamicTariff factory with shared infrastructure.

    Provides unified infrastructure for all tariff providers including:
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
            logger.debug("Created shared cache manager for tariff providers")

        if cls._http_client is None:
            cls._http_client = HttpClientManager()
            logger.debug("Created shared HTTP client for tariff providers")

        if cls._rate_limit_manager is None:
            cls._rate_limit_manager = RateLimitManager()
            logger.debug("Created shared rate limit manager for tariff providers")

        return cls._cache_manager, cls._http_client, cls._rate_limit_manager

    @staticmethod
    def create_tarif_provider(
        config: dict,
        timezone,
        min_time_between_api_calls: int,
        delay_evaluation_by_seconds: int
    ) -> TariffInterface:
        """
        Create and configure a dynamic tariff provider.

        Args:
            config: Configuration dictionary containing provider type and parameters
            timezone: Timezone information
            min_time_between_api_calls: Minimum time interval between API calls
            delay_evaluation_by_seconds: Random delay for API calls

        Returns:
            TariffInterface: Configured tariff provider instance

        Raises:
            RuntimeError: If required configuration fields are missing or provider type is unknown
        """
        provider = config.get('type')
        if not provider:
            raise RuntimeError('[DynamicTariff] Provider type not specified in configuration')

        # Get shared infrastructure for providers
        (cache_manager, http_client,
         rate_limit_manager) = DynamicTariff._get_shared_infrastructure()
        logger.debug("Creating %s provider with shared infrastructure", provider)

        selected_tariff = None

        if provider.lower() in ['awattar_at', 'awattar_de']:
            required_fields = ['vat', 'markup', 'fees']
            for field in required_fields:
                if field not in config.keys():
                    raise RuntimeError(
                        f'[DynTariff] Please include {field} in your configuration file'
                    )

            vat = float(config.get('vat', 0))
            markup = float(config.get('markup', 0))
            fees = float(config.get('fees', 0))

            # Extract country code from provider name
            country = 'at' if provider.lower() == 'awattar_at' else 'de'

            selected_tariff = Awattar(
                timezone,
                country,
                min_time_between_api_calls,
                delay_evaluation_by_seconds,
                shared_cache_manager=cache_manager,
                shared_http_client=http_client
            )

            selected_tariff.set_price_parameters(vat, fees, markup)

        elif provider.lower() == 'tibber':
            if 'apikey' not in config.keys():
                raise RuntimeError(
                    '[Dynamic Tariff] Tibber requires an API token. '
                    'Please provide "apikey :YOURKEY" in your configuration file'
                )

            token = config.get('apikey')

            selected_tariff = Tibber(
                timezone,
                token,
                min_time_between_api_calls,
                delay_evaluation_by_seconds,
                shared_cache_manager=cache_manager,
                shared_http_client=http_client
            )

        elif provider.lower() == 'evcc':
            if 'url' not in config.keys():
                raise RuntimeError(
                    '[Dynamic Tariff] evcc requires an URL. '
                    'Please provide "url" in your configuration file, '
                    'like http://evcc.local/api/tariff/grid'
                )

            selected_tariff = Evcc(
                timezone,
                config.get('url'),
                min_time_between_api_calls,
                delay_evaluation_by_seconds,
                shared_cache_manager=cache_manager,
                shared_http_client=http_client
            )
        else:
            raise RuntimeError(f'[DynamicTariff] Unknown provider {provider}')

        if selected_tariff is None:
            raise RuntimeError(f'[DynamicTariff] Failed to create provider for {provider}')

        logger.info("Created %s tariff provider", provider)
        return selected_tariff

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
            logger.info("Cleared all cached data for tariff providers")
