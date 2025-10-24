"""
Batcontrol Fetching Package

This package provides common infrastructure for data fetching from external APIs,
including caching, rate limiting, HTTP client management, and error handling.

Components:
- constants: Common constants for timeouts, cache durations, etc.
- cache_manager: Centralized caching with thread-safe operations
- http_client: HTTP client with unified delay, timeout, and rate-limit handling
- base_fetcher: Base class for all data providers with common patterns
- rate_limit_manager: Centralized rate limit management across providers
"""

from .constants import (
    EXTERNAL_API_TIMEOUT,
    LOCAL_API_TIMEOUT,
    DEFAULT_CACHE_DURATION,
    LOCAL_CACHE_DURATION,
    DEFAULT_MAX_DELAY,
    DEFAULT_RETRY_COUNT,
    PROVIDER_TYPE_EXTERNAL,
    PROVIDER_TYPE_LOCAL
)

from .base_fetcher import BaseFetcher
from .cache_manager import CacheManager
from .http_client import HttpClientManager
from .rate_limit_manager import RateLimitManager

__all__ = [
    'EXTERNAL_API_TIMEOUT',
    'LOCAL_API_TIMEOUT', 
    'DEFAULT_CACHE_DURATION',
    'LOCAL_CACHE_DURATION',
    'DEFAULT_MAX_DELAY',
    'DEFAULT_RETRY_COUNT',
    'PROVIDER_TYPE_EXTERNAL',
    'PROVIDER_TYPE_LOCAL',
    'BaseFetcher',
    'CacheManager',
    'HttpClientManager',
    'RateLimitManager'
]
