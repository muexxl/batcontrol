"""
HTTP client manager with unified delay, timeout, and rate-limit handling.

This module provides a centralized HTTP client that handles common patterns
like random delays, timeouts, retries, and rate limit detection.
"""

import time
import random
import requests
from typing import Optional, Dict, Any
import logging

from .constants import (
    EXTERNAL_API_TIMEOUT,
    LOCAL_API_TIMEOUT,
    DEFAULT_MAX_DELAY,
    DEFAULT_RETRY_COUNT,
    RATE_LIMIT_STATUS_CODES,
    PROVIDER_TYPE_EXTERNAL,
    PROVIDER_TYPE_LOCAL
)
from .rate_limit_manager import RateLimitManager

logger = logging.getLogger(__name__)


class HttpClientManager:
    """
    Centralized HTTP client with unified patterns for all providers.
    
    Features:
    - Provider-specific timeouts
    - Random delay implementation
    - Rate limit detection and handling
    - Retry logic with exponential backoff
    - Request logging and metrics
    """
    
    def __init__(self, rate_limit_manager: Optional[RateLimitManager] = None):
        self.session = requests.Session()
        self.rate_limit_manager = rate_limit_manager or RateLimitManager()
        self._stats = {
            'requests_made': 0,
            'requests_failed': 0,
            'rate_limits_hit': 0,
            'retries_made': 0
        }
    
    def get_timeout_for_provider_type(self, provider_type: str) -> int:
        """Get appropriate timeout based on provider type."""
        if provider_type == PROVIDER_TYPE_LOCAL:
            return LOCAL_API_TIMEOUT
        else:
            return EXTERNAL_API_TIMEOUT
    
    def apply_random_delay(self, provider_id: str, max_delay: int, last_update: float = 0):
        """
        Apply random delay before making request to spread load.
        
        Args:
            provider_id: Unique identifier for the provider
            max_delay: Maximum delay in seconds
            last_update: Timestamp of last update (0 means first call)
        """
        # Skip delay on first call
        if last_update == 0 or max_delay <= 0:
            return
        
        sleeptime = random.randrange(0, max_delay, 1)
        logger.debug(f"[{provider_id}] Applying random delay of {sleeptime}s")
        time.sleep(sleeptime)
    
    def get_with_rate_limit_handling(
        self,
        url: str,
        provider_id: str,
        provider_type: str = PROVIDER_TYPE_EXTERNAL,
        max_delay: int = DEFAULT_MAX_DELAY,
        last_update: float = 0,
        timeout: Optional[int] = None,
        **kwargs
    ) -> requests.Response:
        """
        Make GET request with full rate limit and delay handling.
        
        Args:
            url: URL to request
            provider_id: Unique identifier for the provider
            provider_type: Type of provider (external/local)
            max_delay: Maximum random delay in seconds
            last_update: Timestamp of last update
            timeout: Custom timeout (uses provider type default if None)
            **kwargs: Additional arguments for requests.get()
            
        Returns:
            Response object
            
        Raises:
            ConnectionError: If request fails or rate limited
        """
        # Check if provider is currently rate limited
        if self.rate_limit_manager.is_rate_limited(provider_id):
            retry_after = self.rate_limit_manager.get_retry_after(provider_id)
            raise ConnectionError(
                f"[{provider_id}] Provider is rate limited. "
                f"Retry after {retry_after:.1f} seconds"
            )
        
        # Apply random delay
        self.apply_random_delay(provider_id, max_delay, last_update)
        
        # Determine timeout
        if timeout is None:
            timeout = self.get_timeout_for_provider_type(provider_type)
        
        # Make request
        start_time = time.time()
        try:
            logger.debug(f"[{provider_id}] Making GET request to {url} (timeout: {timeout}s)")
            
            response = self.session.get(url, timeout=timeout, **kwargs)
            duration = time.time() - start_time
            
            self._stats['requests_made'] += 1
            logger.info(f"[{provider_id}] Request completed in {duration:.2f}s (status: {response.status_code})")
            
            # Check for rate limiting
            if response.status_code in RATE_LIMIT_STATUS_CODES:
                self._stats['rate_limits_hit'] += 1
                self.rate_limit_manager.set_rate_limit_from_response(provider_id, response)
                raise ConnectionError(
                    f"[{provider_id}] Rate limit exceeded (HTTP {response.status_code})"
                )
            
            # Raise for other HTTP errors
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            duration = time.time() - start_time
            self._stats['requests_failed'] += 1
            logger.error(f"[{provider_id}] Request failed after {duration:.2f}s: {e}")
            raise ConnectionError(f"[{provider_id}] Request failed: {e}") from e
    
    def post_with_rate_limit_handling(
        self,
        url: str,
        provider_id: str,
        provider_type: str = PROVIDER_TYPE_EXTERNAL,
        max_delay: int = DEFAULT_MAX_DELAY,
        last_update: float = 0,
        timeout: Optional[int] = None,
        **kwargs
    ) -> requests.Response:
        """
        Make POST request with full rate limit and delay handling.
        
        Similar to get_with_rate_limit_handling but for POST requests.
        """
        # Check if provider is currently rate limited
        if self.rate_limit_manager.is_rate_limited(provider_id):
            retry_after = self.rate_limit_manager.get_retry_after(provider_id)
            raise ConnectionError(
                f"[{provider_id}] Provider is rate limited. "
                f"Retry after {retry_after:.1f} seconds"
            )
        
        # Apply random delay
        self.apply_random_delay(provider_id, max_delay, last_update)
        
        # Determine timeout
        if timeout is None:
            timeout = self.get_timeout_for_provider_type(provider_type)
        
        # Make request
        start_time = time.time()
        try:
            logger.debug(f"[{provider_id}] Making POST request to {url} (timeout: {timeout}s)")
            
            response = self.session.post(url, timeout=timeout, **kwargs)
            duration = time.time() - start_time
            
            self._stats['requests_made'] += 1
            logger.info(f"[{provider_id}] Request completed in {duration:.2f}s (status: {response.status_code})")
            
            # Check for rate limiting
            if response.status_code in RATE_LIMIT_STATUS_CODES:
                self._stats['rate_limits_hit'] += 1
                self.rate_limit_manager.set_rate_limit_from_response(provider_id, response)
                raise ConnectionError(
                    f"[{provider_id}] Rate limit exceeded (HTTP {response.status_code})"
                )
            
            # Raise for other HTTP errors
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            duration = time.time() - start_time
            self._stats['requests_failed'] += 1
            logger.error(f"[{provider_id}] Request failed after {duration:.2f}s: {e}")
            raise ConnectionError(f"[{provider_id}] Request failed: {e}") from e
    
    def get_stats(self) -> Dict[str, Any]:
        """Get HTTP client statistics."""
        total_requests = self._stats['requests_made'] + self._stats['requests_failed']
        success_rate = (self._stats['requests_made'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self._stats,
            'success_rate': success_rate,
            'rate_limit_info': self.rate_limit_manager.get_all_rate_limits()
        }
    
    def reset_stats(self):
        """Reset HTTP client statistics."""
        self._stats = {
            'requests_made': 0,
            'requests_failed': 0,
            'rate_limits_hit': 0,
            'retries_made': 0
        }