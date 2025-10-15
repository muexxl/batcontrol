"""
Unified Provider Manager for shared infrastructure coordination.

This module provides a centralized manager for all provider infrastructure,
ensuring singleton instances and coordinated resource management across
all forecast providers (solar, tariff, consumption).

Features:
- Global singleton infrastructure management
- Unified cache statistics and monitoring
- Thread-safe resource coordination
- Graceful shutdown and cleanup
- Provider-agnostic API calls and monitoring
"""
import logging
import threading
from typing import Dict, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
import time
import schedule

from .fetching.cache_manager import CacheManager
from .fetching.http_client import HttpClientManager
from .fetching.rate_limit_manager import RateLimitManager

logger = logging.getLogger(__name__)

class ProviderManager:
    """
    Global manager for provider infrastructure and coordination.
    
    Manages shared resources and provides unified APIs for:
    - Cache management across all providers
    - HTTP client coordination
    - Rate limit management
    - Background threading for parallel provider calls
    - Monitoring and statistics
    """
    
    _instance: Optional['ProviderManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton implementation with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the provider manager (only once due to singleton)."""
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self._cache_manager: Optional[CacheManager] = None
        self._http_client: Optional[HttpClientManager] = None
        self._rate_limit_manager: Optional[RateLimitManager] = None
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._shutdown = False
        
        # Background fetching infrastructure
        self._background_thread: Optional[threading.Thread] = None
        self._background_fetchers: Dict[str, Callable] = {}
        self._background_intervals: Dict[str, int] = {}
        self._background_running = False
        self._background_lock = threading.Lock()
        self._scheduler = schedule.Scheduler()
        
        logger.info("Initialized ProviderManager singleton")
    
    def get_cache_manager(self) -> CacheManager:
        """Get or create the global cache manager."""
        if self._cache_manager is None:
            with self._lock:
                if self._cache_manager is None:
                    self._cache_manager = CacheManager()
                    logger.debug("Created global cache manager")
        return self._cache_manager
    
    def get_http_client(self) -> HttpClientManager:
        """Get or create the global HTTP client."""
        if self._http_client is None:
            with self._lock:
                if self._http_client is None:
                    self._http_client = HttpClientManager()
                    logger.debug("Created global HTTP client")
        return self._http_client
    
    def get_rate_limit_manager(self) -> RateLimitManager:
        """Get or create the global rate limit manager."""
        if self._rate_limit_manager is None:
            with self._lock:
                if self._rate_limit_manager is None:
                    self._rate_limit_manager = RateLimitManager()
                    logger.debug("Created global rate limit manager")
        return self._rate_limit_manager
    
    def get_thread_pool(self, max_workers: int = 4) -> ThreadPoolExecutor:
        """
        Get or create the global thread pool for parallel provider calls.
        
        Args:
            max_workers: Maximum number of worker threads
            
        Returns:
            ThreadPoolExecutor: Global thread pool instance
        """
        if self._thread_pool is None or self._thread_pool._shutdown:
            with self._lock:
                if self._thread_pool is None or self._thread_pool._shutdown:
                    self._thread_pool = ThreadPoolExecutor(
                        max_workers=max_workers,
                        thread_name_prefix="provider_"
                    )
                    logger.debug(f"Created global thread pool with {max_workers} workers")
        return self._thread_pool
    
    def fetch_parallel(
        self, 
        provider_calls: Dict[str, callable], 
        timeout: float = 60.0,
        fail_fast: bool = False
    ) -> Dict[str, Any]:
        """
        Execute multiple provider calls in parallel.
        
        Args:
            provider_calls: Dict mapping provider names to callable functions
            timeout: Total timeout for all calls
            fail_fast: If True, raise exception on first failure
            
        Returns:
            Dict mapping provider names to results or exceptions
            
        Example:
            results = provider_manager.fetch_parallel({
                'solar': lambda: solar_provider.get_forecast(),
                'tariff': lambda: tariff_provider.get_prices(),
                'consumption': lambda: consumption_provider.get_forecast()
            })
        """
        if self._shutdown:
            raise RuntimeError("ProviderManager is shut down")
        
        thread_pool = self.get_thread_pool()
        futures = {}
        results = {}
        
        # Submit all calls
        start_time = time.time()
        for name, call_func in provider_calls.items():
            future = thread_pool.submit(call_func)
            futures[name] = future
            logger.debug(f"Submitted {name} provider call to thread pool")
        
        # Collect results with timeout
        try:
            for name, future in futures.items():
                remaining_timeout = max(0, timeout - (time.time() - start_time))
                try:
                    result = future.result(timeout=remaining_timeout)
                    results[name] = result
                    logger.debug(f"Successfully fetched {name} provider data")
                except Exception as e:
                    logger.warning(f"Failed to fetch {name} provider data: {e}")
                    results[name] = e
                    if fail_fast:
                        # Cancel remaining futures
                        for remaining_name, remaining_future in futures.items():
                            if remaining_name != name and not remaining_future.done():
                                remaining_future.cancel()
                        raise e
                        
        except Exception as e:
            logger.error(f"Error in parallel fetch: {e}")
            # Cancel any remaining futures
            for future in futures.values():
                if not future.done():
                    future.cancel()
            raise
        
        total_time = time.time() - start_time
        success_count = sum(1 for result in results.values() if not isinstance(result, Exception))
        logger.info(f"Parallel fetch completed: {success_count}/{len(provider_calls)} successful in {total_time:.2f}s")
        
        return results
    
    def register_background_fetcher(
        self, 
        provider_id: str, 
        fetch_func: Callable, 
        interval_seconds: int = 900,  # Changed from interval_minutes to interval_seconds
        provider_instance: Optional[Any] = None
    ):
        """
        Register a provider for background fetching.
        
        Args:
            provider_id: Unique identifier for the provider
            fetch_func: Function to call for fetching data
            interval_seconds: How often to fetch in seconds
            provider_instance: The actual provider instance for cache access
        """
        with self._background_lock:
            self._background_fetchers[provider_id] = {
                'fetch_func': fetch_func,
                'provider_instance': provider_instance,
                'last_success': None,
                'last_data': None
            }
            self._background_intervals[provider_id] = interval_seconds
            
            # Schedule the fetcher if background is running
            if self._background_running:
                # Convert seconds to minutes for scheduler
                interval_minutes = interval_seconds // 60
                self._scheduler.every(interval_minutes).minutes.do(
                    self._safe_background_fetch, provider_id
                ).tag(provider_id)
                
        logger.info(f"Registered {provider_id} for background fetching every {interval_seconds} seconds")
    
    def start_background_fetching(self):
        """Start the background fetching thread."""
        if self._background_running:
            logger.warning("Background fetching already running")
            return
            
        with self._background_lock:
            self._background_running = True
            
            # Schedule all registered fetchers
            for provider_id, provider_info in self._background_fetchers.items():
                interval = self._background_intervals[provider_id]
                self._scheduler.every(interval).minutes.do(
                    self._safe_background_fetch, provider_id
                ).tag(provider_id)
                
                # Run immediately for initial data
                self.get_thread_pool().submit(
                    self._safe_background_fetch, provider_id
                )
            
            # Start scheduler thread
            self._background_thread = threading.Thread(
                target=self._run_background_scheduler,
                name="provider_background_scheduler",
                daemon=True
            )
            self._background_thread.start()
            
        logger.info("Started background fetching for all registered providers")
    
    def stop_background_fetching(self):
        """Stop the background fetching thread."""
        with self._background_lock:
            if not self._background_running:
                return
                
            self._background_running = False
            self._scheduler.clear()
            
        if self._background_thread and self._background_thread.is_alive():
            self._background_thread.join(timeout=5.0)
            
        logger.info("Stopped background fetching")
    
    def _run_background_scheduler(self):
        """Run the background scheduler in a separate thread."""
        logger.debug("Background scheduler thread started")
        
        while self._background_running:
            try:
                self._scheduler.run_pending()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in background scheduler: {e}", exc_info=True)
                
        logger.debug("Background scheduler thread stopped")
    
    def _safe_background_fetch(self, provider_id: str):
        """Safely execute a background fetch with error handling."""
        try:
            logger.debug(f"Starting background fetch for {provider_id}")
            start_time = time.time()
            
            provider_info = self._background_fetchers.get(provider_id)
            if not provider_info:
                logger.warning(f"No provider info found for {provider_id}")
                return
            
            fetch_func = provider_info['fetch_func']
            result = fetch_func()
            
            # Store the result for later retrieval
            with self._background_lock:
                self._background_fetchers[provider_id]['last_success'] = time.time()
                self._background_fetchers[provider_id]['last_data'] = result
            
            duration = time.time() - start_time
            logger.debug(f"Background fetch for {provider_id} completed in {duration:.2f}s")
            
        except Exception as e:
            logger.warning(f"Background fetch failed for {provider_id}: {e}")
    
    def get_cached_data_non_blocking(self, provider_id: str) -> Optional[Any]:
        """
        Get cached data for a provider without triggering a fetch.
        
        Args:
            provider_id: Provider identifier
            
        Returns:
            Cached data if available, None otherwise
        """
        with self._background_lock:
            provider_info = self._background_fetchers.get(provider_id)
            if provider_info and provider_info['last_data'] is not None:
                return provider_info['last_data']
        
        # Fallback: try to get from cache manager if we have provider instance
        if self._cache_manager is None:
            return None
            
        try:
            provider_info = self._background_fetchers.get(provider_id)
            if provider_info and provider_info['provider_instance']:
                # Try to access cache through provider's cache key
                provider_instance = provider_info['provider_instance']
                if hasattr(provider_instance, '_cache_key'):
                    return self._cache_manager.get(provider_instance._cache_key)
        except Exception as e:
            logger.debug(f"Error getting cached data for {provider_id}: {e}")
            
        return None
    
    def get_provider_data_async(
        self, 
        provider_calls: Dict[str, Callable],
        use_cache_first: bool = True,
        max_cache_age_seconds: int = 900  # Changed from max_cache_age_minutes to seconds
    ) -> Dict[str, Any]:
        """
        Get provider data asynchronously with cache-first strategy.
        
        Args:
            provider_calls: Dict mapping provider names to callable functions
            use_cache_first: If True, return cached data immediately if available
            max_cache_age_seconds: Maximum acceptable age for cached data in seconds
            
        Returns:
            Dict mapping provider names to results (cached or fresh)
        """
        results = {}
        
        for provider_name, fetch_func in provider_calls.items():
            if use_cache_first:
                # Try to get cached data first
                cached_data = self.get_cached_data_non_blocking(provider_name)
                if cached_data is not None and self.is_data_fresh(provider_name, max_cache_age_seconds):
                    results[provider_name] = cached_data
                    logger.debug(f"Using cached data for {provider_name}")
                    continue
            
            # If no cached data or too old, fetch in background
            if self._background_running and provider_name in self._background_fetchers:
                # Background fetching is active - we should have recent data
                cached_data = self.get_cached_data_non_blocking(provider_name)
                if cached_data is not None:
                    results[provider_name] = cached_data
                    logger.debug(f"Using background-fetched data for {provider_name}")
                    continue
            
            # Fallback: fetch synchronously
            try:
                logger.debug(f"Fallback synchronous fetch for {provider_name}")
                results[provider_name] = fetch_func()
            except Exception as e:
                logger.error(f"Failed to fetch {provider_name}: {e}")
                results[provider_name] = e
        
        return results
    
    def is_data_fresh(self, provider_id: str, max_age_seconds: int = 900) -> bool:
        """
        Check if cached data for a provider is fresh enough.
        
        Args:
            provider_id: Provider identifier
            max_age_seconds: Maximum acceptable age in seconds
            
        Returns:
            True if data is fresh, False otherwise
        """
        with self._background_lock:
            provider_info = self._background_fetchers.get(provider_id)
            if not provider_info or provider_info['last_success'] is None:
                return False
            
            age_seconds = time.time() - provider_info['last_success']
            
            return age_seconds <= max_age_seconds
    
    def get_global_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics across all infrastructure components.
        
        Returns:
            Dict containing cache stats, rate limits, thread pool status, etc.
        """
        stats = {
            'provider_manager': {
                'initialized': self._initialized,
                'shutdown': self._shutdown,
                'timestamp': time.time()
            }
        }
        
        # Cache statistics
        if self._cache_manager is not None:
            stats['cache'] = self._cache_manager.get_stats()
        else:
            stats['cache'] = {'status': 'not_initialized'}
        
        # Rate limit statistics
        if self._rate_limit_manager is not None:
            stats['rate_limits'] = self._rate_limit_manager.get_all_rate_limits()
        else:
            stats['rate_limits'] = {'status': 'not_initialized'}
        
        # Thread pool statistics
        if self._thread_pool is not None and not self._thread_pool._shutdown:
            stats['thread_pool'] = {
                'max_workers': self._thread_pool._max_workers,
                'active_threads': getattr(self._thread_pool, '_threads', 0),
                'shutdown': self._thread_pool._shutdown
            }
        else:
            stats['thread_pool'] = {'status': 'not_initialized_or_shutdown'}
        
        return stats
    
    def clear_all_caches(self):
        """Clear all cached data across all providers."""
        if self._cache_manager is not None:
            self._cache_manager.clear()
            logger.info("Cleared all cached data globally")
        else:
            logger.warning("Cache manager not initialized, nothing to clear")
    
    def reset_rate_limits(self):
        """Reset all rate limits across all providers."""
        if self._rate_limit_manager is not None:
            self._rate_limit_manager.clear_all()
            logger.info("Reset all rate limits globally")
        else:
            logger.warning("Rate limit manager not initialized, nothing to reset")
    
    def health_check(self) -> Dict[str, bool]:
        """
        Perform health check on all infrastructure components.
        
        Returns:
            Dict mapping component names to health status
        """
        health = {}
        
        # Cache manager health
        try:
            if self._cache_manager is not None:
                # Test basic cache operation
                test_key = "__health_check__"
                self._cache_manager.set(test_key, "test", ttl=1)
                health['cache_manager'] = self._cache_manager.get(test_key) == "test"
                self._cache_manager.invalidate(test_key)
            else:
                health['cache_manager'] = False
        except Exception as e:
            logger.warning(f"Cache manager health check failed: {e}")
            health['cache_manager'] = False
        
        # HTTP client health
        try:
            health['http_client'] = self._http_client is not None
        except Exception as e:
            logger.warning(f"HTTP client health check failed: {e}")
            health['http_client'] = False
        
        # Rate limit manager health
        try:
            health['rate_limit_manager'] = self._rate_limit_manager is not None
        except Exception as e:
            logger.warning(f"Rate limit manager health check failed: {e}")
            health['rate_limit_manager'] = False
        
        # Thread pool health
        try:
            health['thread_pool'] = (
                self._thread_pool is not None and 
                not self._thread_pool._shutdown
            )
        except Exception as e:
            logger.warning(f"Thread pool health check failed: {e}")
            health['thread_pool'] = False
        
        all_healthy = all(health.values())
        logger.debug(f"Health check completed: {'all healthy' if all_healthy else 'issues detected'}")
        
        return health
    
    def shutdown(self):
        """Gracefully shutdown all infrastructure components."""
        if self._shutdown:
            return
        
        logger.info("Shutting down ProviderManager")
        self._shutdown = True
        
        # Stop background fetching first
        self.stop_background_fetching()
        
        # Shutdown thread pool
        if self._thread_pool is not None:
            self._thread_pool.shutdown(wait=True)
            logger.debug("Thread pool shut down")
        
        # Clear caches
        if self._cache_manager is not None:
            self._cache_manager.clear()
            logger.debug("Cleared all caches during shutdown")
        
        logger.info("ProviderManager shutdown complete")
    
    def __del__(self):
        """Cleanup on garbage collection."""
        if hasattr(self, '_shutdown') and not self._shutdown:
            self.shutdown()

# Global singleton instance accessor
def get_provider_manager() -> ProviderManager:
    """Get the global ProviderManager singleton instance."""
    return ProviderManager()