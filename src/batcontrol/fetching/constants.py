"""
Constants for the batcontrol fetching infrastructure.

This module defines common timeout values, cache durations, and other
configuration constants used across all data providers.

Cache Strategy Overview:
- Cache TTL: How long data stays valid in cache (24 hours = 86400 seconds)
- Refresh Interval: How often background fetching updates data (900-1800 seconds)
- Background fetching ensures data is always fresh without additional cache age checks
"""

# Timeout constants (in seconds)
EXTERNAL_API_TIMEOUT = 30  # For all external APIs (Awattar, Tibber, forecast.solar, etc.)
LOCAL_API_TIMEOUT = 10     # For local APIs (EVCC, local services)

# Cache TTL constants (in seconds) - how long data stays valid in cache
EXTERNAL_CACHE_TTL = 86400      # 24 hours - external APIs cache TTL
LOCAL_CACHE_TTL = 86400         # 24 hours - local APIs cache TTL
SOLAR_FORECAST_MIN_DURATION = 64800  # 18 hours minimum forecast duration for PV providers

# Refresh interval constants (in seconds) - how often to update data in background
EXTERNAL_REFRESH_INTERVAL = 1800    # 30 minutes - external APIs refresh interval
LOCAL_REFRESH_INTERVAL = 900        # 15 minutes - local APIs refresh interval

# Legacy constants for backward compatibility
DEFAULT_CACHE_DURATION = EXTERNAL_CACHE_TTL
LOCAL_CACHE_DURATION = LOCAL_CACHE_TTL

# Rate limiting and delay constants
DEFAULT_MAX_DELAY = 15         # Maximum random delay in seconds
DEFAULT_RETRY_COUNT = 3        # Default number of retries for failed requests
RATE_LIMIT_BACKOFF_FACTOR = 2  # Exponential backoff factor

# Parallel fetching constants
PARALLEL_FETCH_TIMEOUT = 60.0  # Total timeout for parallel provider fetching

# Provider type constants
PROVIDER_TYPE_EXTERNAL = "external"
PROVIDER_TYPE_LOCAL = "local"

# HTTP status codes for rate limiting
RATE_LIMIT_STATUS_CODES = [429, 503]

# Common headers for rate limit detection
RATE_LIMIT_HEADERS = [
    'X-Ratelimit-Retry-At',
    'Retry-After',
    'X-RateLimit-Reset',
    'RateLimit-Reset',
    'X-Rate-Limit-Reset'
]
