"""
Rate limit manager for tracking and enforcing API rate limits.

This module provides centralized rate limit management across all providers,
supporting various rate limit headers and backoff strategies.
"""

import time
import datetime
import threading
import logging
from typing import Optional, Dict, Any

from .constants import RATE_LIMIT_HEADERS

logger = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class RateLimitInfo:
    """Information about a rate limit event."""

    def __init__(self, retry_after: float, reset_time: Optional[datetime.datetime] = None):
        self.retry_after = retry_after  # Seconds to wait
        self.reset_time = reset_time    # When rate limit resets
        self.created_at = time.time()


class RateLimitManager:
    """
    Centralized rate limit management for all API providers.

    Features:
    - Provider-specific rate limit tracking
    - Support for various rate limit headers
    - Automatic blackout window management
    - Thread-safe operations
    """

    def __init__(self):
        self._rate_limits: Dict[str, RateLimitInfo] = {}
        self._lock = threading.Lock()

    def is_rate_limited(self, provider_id: str) -> bool:
        """
        Check if a provider is currently rate limited.

        Args:
            provider_id: Unique identifier for the provider

        Returns:
            True if provider is rate limited, False otherwise
        """
        with self._lock:
            if provider_id not in self._rate_limits:
                return False

            rate_limit_info = self._rate_limits[provider_id]
            current_time = time.time()

            # Check if rate limit has expired
            if current_time >= rate_limit_info.created_at + rate_limit_info.retry_after:
                del self._rate_limits[provider_id]
                logger.info("Rate limit expired for provider: %s", provider_id)
                return False

            remaining_time = (
                (rate_limit_info.created_at + rate_limit_info.retry_after)
                - current_time
            )
            logger.debug(
                "Provider %s is rate limited for %.1f more seconds",
                provider_id, remaining_time
            )
            return True

    def get_retry_after(self, provider_id: str) -> Optional[float]:
        """
        Get the time to wait before retrying for a rate limited provider.

        Args:
            provider_id: Unique identifier for the provider

        Returns:
            Seconds to wait, or None if not rate limited
        """
        with self._lock:
            if provider_id not in self._rate_limits:
                return None

            rate_limit_info = self._rate_limits[provider_id]
            current_time = time.time()
            remaining_time = (
                (rate_limit_info.created_at + rate_limit_info.retry_after)
                - current_time
            )

            return max(0, remaining_time)

    # pylint: disable=too-many-branches
    def set_rate_limit_from_response(
        self, provider_id: str, response
    ) -> Optional[RateLimitInfo]:
        """
        Parse rate limit information from HTTP response headers.

        Args:
            provider_id: Unique identifier for the provider
            response: HTTP response object with headers

        Returns:
            RateLimitInfo if rate limit detected, None otherwise
        """
        if not hasattr(response, 'headers'):
            return None

        headers = response.headers
        rate_limit_info = None

        # Check for X-Ratelimit-Retry-At (forecast.solar format)
        if 'X-Ratelimit-Retry-At' in headers:
            retry_at_str = headers['X-Ratelimit-Retry-At']
            try:
                retry_at_timestamp = datetime.datetime.fromisoformat(retry_at_str)
                retry_after = (
                    retry_at_timestamp - datetime.datetime.now().astimezone()
                ).total_seconds()
                rate_limit_info = RateLimitInfo(retry_after, retry_at_timestamp)
                logger.info(
                    "Parsed X-Ratelimit-Retry-At for %s: retry after %.1fs",
                    provider_id, retry_after
                )
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse X-Ratelimit-Retry-At header: %s", e)

        # Check for standard Retry-After header
        elif 'Retry-After' in headers:
            retry_after_str = headers['Retry-After']
            try:
                # Retry-After can be in seconds or HTTP date
                if retry_after_str.isdigit():
                    retry_after = float(retry_after_str)
                else:
                    # Parse HTTP date format
                    retry_at_timestamp = datetime.datetime.strptime(
                        retry_after_str, '%a, %d %b %Y %H:%M:%S %Z'
                    )
                    retry_after = (
                        retry_at_timestamp - datetime.datetime.now()
                    ).total_seconds()

                rate_limit_info = RateLimitInfo(retry_after)
                logger.info(
                    "Parsed Retry-After for %s: retry after %.1fs",
                    provider_id, retry_after
                )
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse Retry-After header: %s", e)

        # Check for other rate limit reset headers
        else:
            for header_name in RATE_LIMIT_HEADERS:
                if header_name in headers:
                    try:
                        reset_time_str = headers[header_name]
                        # Try parsing as timestamp first
                        if reset_time_str.isdigit():
                            reset_timestamp = int(reset_time_str)
                            retry_after = reset_timestamp - time.time()
                        else:
                            # Try parsing as ISO date
                            reset_datetime = datetime.datetime.fromisoformat(
                                reset_time_str
                            )
                            retry_after = (
                                reset_datetime - datetime.datetime.now().astimezone()
                            ).total_seconds()

                        if retry_after > 0:
                            rate_limit_info = RateLimitInfo(retry_after)
                            logger.info(
                                "Parsed %s for %s: retry after %.1fs",
                                header_name, provider_id, retry_after
                            )
                            break
                    except (ValueError, TypeError) as e:
                        logger.debug("Failed to parse %s header: %s", header_name, e)

        # Store rate limit info if found
        if rate_limit_info:
            with self._lock:
                self._rate_limits[provider_id] = rate_limit_info

            logger.warning(
                "Rate limit set for provider %s: retry after %.1f seconds",
                provider_id, rate_limit_info.retry_after
            )

        return rate_limit_info

    def set_rate_limit_manual(self, provider_id: str, retry_after: float):
        """
        Manually set a rate limit for a provider.

        Args:
            provider_id: Unique identifier for the provider
            retry_after: Seconds to wait before retrying
        """
        rate_limit_info = RateLimitInfo(retry_after)

        with self._lock:
            self._rate_limits[provider_id] = rate_limit_info

        logger.warning(
            "Manual rate limit set for provider %s: retry after %.1fs",
            provider_id, retry_after
        )

    def clear_rate_limit(self, provider_id: str):
        """Remove rate limit for a specific provider."""
        with self._lock:
            if provider_id in self._rate_limits:
                del self._rate_limits[provider_id]
                logger.info("Rate limit cleared for provider: %s", provider_id)

    def clear_all(self):
        """Clear all rate limits."""
        with self._lock:
            self._rate_limits.clear()
        logger.info("All rate limits cleared")

    def get_all_rate_limits(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active rate limits."""
        current_time = time.time()
        result = {}

        with self._lock:
            for provider_id, rate_limit_info in self._rate_limits.items():
                remaining_time = (
                    (rate_limit_info.created_at + rate_limit_info.retry_after)
                    - current_time
                )
                result[provider_id] = {
                    'remaining_seconds': max(0, remaining_time),
                    'reset_time': rate_limit_info.reset_time,
                    'created_at': rate_limit_info.created_at
                }

        return result
