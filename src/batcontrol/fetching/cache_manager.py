"""
Thread-safe cache manager for data providers.

This module provides centralized caching functionality with thread-safe operations,
cache expiration, and memory management.
"""

import time
import threading
from typing import Any, Optional, Dict, Callable
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Thread-safe cache manager for storing API responses and other data.
    
    Features:
    - Thread-safe operations using locks
    - Automatic cache expiration based on TTL
    - Memory-efficient storage
    - Cache hit/miss metrics for monitoring
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'stores': 0,
            'expires': 0
        }
    
    def _get_lock(self, key: str) -> threading.Lock:
        """Get or create a lock for the given key."""
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache if it exists and hasn't expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if available and valid, None otherwise
        """
        lock = self._get_lock(key)
        with lock:
            if key not in self._cache:
                self._stats['misses'] += 1
                return None
            
            cache_entry = self._cache[key]
            current_time = time.time()
            
            # Check if cache entry has expired
            if current_time > cache_entry['expires_at']:
                del self._cache[key]
                self._stats['expires'] += 1
                self._stats['misses'] += 1
                logger.debug(f"Cache entry expired for key: {key}")
                return None
            
            self._stats['hits'] += 1
            logger.debug(f"Cache hit for key: {key}")
            return cache_entry['value']
    
    def set(self, key: str, value: Any, ttl: int):
        """
        Store a value in cache with TTL (time to live).
        
        Args:
            key: Cache key
            value: Value to store
            ttl: Time to live in seconds
        """
        lock = self._get_lock(key)
        with lock:
            expires_at = time.time() + ttl
            self._cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'stored_at': time.time()
            }
            self._stats['stores'] += 1
            logger.debug(f"Cached value for key: {key} (TTL: {ttl}s)")
    
    def get_or_fetch(self, key: str, fetch_func: Callable[[], Any], ttl: int) -> Any:
        """
        Get value from cache or fetch using the provided function.
        
        Args:
            key: Cache key
            fetch_func: Function to call if cache miss
            ttl: Time to live for newly fetched data
            
        Returns:
            Cached or freshly fetched value
        """
        # Try cache first
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value
        
        # Cache miss - fetch new data
        logger.debug(f"Cache miss for key: {key}, fetching new data")
        try:
            fresh_value = fetch_func()
            self.set(key, fresh_value, ttl)
            return fresh_value
        except Exception as e:
            logger.error(f"Failed to fetch data for key {key}: {e}")
            raise
    
    def invalidate(self, key: str):
        """Remove a specific key from cache."""
        lock = self._get_lock(key)
        with lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Invalidated cache for key: {key}")
    
    def clear(self):
        """Clear all cache entries."""
        with self._global_lock:
            self._cache.clear()
            self._locks.clear()
            logger.info("Cache cleared")
    
    def cleanup_expired(self):
        """Remove all expired cache entries."""
        current_time = time.time()
        expired_keys = []
        
        with self._global_lock:
            for key, entry in self._cache.items():
                if current_time > entry['expires_at']:
                    expired_keys.append(key)
        
        for key in expired_keys:
            self.invalidate(key)
        
        if expired_keys:
            self._stats['expires'] += len(expired_keys)
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self._stats,
            'hit_rate': hit_rate,
            'cache_size': len(self._cache)
        }
    
    def reset_stats(self):
        """Reset cache statistics."""
        self._stats = {'hits': 0, 'misses': 0, 'stores': 0, 'expires': 0}